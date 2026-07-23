"""
AI Router & Copilot Service — Copilot Routes.

Endpoints:
  POST   /copilot/chat                    — REST fallback for copilot turns
  WS     /copilot/ws/{session_id}         — WebSocket chat (primary)
  GET    /copilot/sessions/{id}/history   — fetch conversation history

Rate-limited: 20 RPM per IP (enforced at app middleware level).
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from libs.db_models.database import get_async_session
from libs.db_models.router_copilot_models import MessageRole
from services.ai_router_copilot_service.config import get_settings
from services.ai_router_copilot_service.copilot_agent import run_copilot_turn
from services.ai_router_copilot_service.repository import (
    append_message,
    fetch_active_listings,
    get_or_create_session,
    get_recent_messages,
    get_session_with_messages,
    save_recommendation,
)
from services.ai_router_copilot_service.schemas import (
    CopilotChatRequest,
    CopilotChatResponse,
    CopilotMessageOut,
    CopilotSessionHistory,
    WSInbound,
    WSOutbound,
)

log = structlog.get_logger(__name__)
settings = get_settings()

copilot_router = APIRouter(prefix="/copilot", tags=["copilot"])
bearer = HTTPBearer(auto_error=False)


def _get_developer_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> uuid.UUID | None:
    if credentials is None:
        return None
    try:
        import jwt
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return uuid.UUID(payload.get("sub")) if payload.get("sub") else None
    except Exception:
        return None


# ── Helper: build listings_fetcher and recommendation_persister closures ──────

def _make_fetcher(session):
    async def _fetch(*, min_gpu_vram_gb=None, region=None):
        return await fetch_active_listings(
            session, min_gpu_vram_gb=min_gpu_vram_gb, region=region
        )
    return _fetch


def _make_persister(session, developer_id):
    async def _persist(*, request_payload, recommended_listing_ids, ranked_results):
        return await save_recommendation(
            session,
            developer_id=developer_id,
            request_payload=request_payload,
            recommended_listing_ids=recommended_listing_ids,
            ranked_results=ranked_results,
        )
    return _persist


# ── POST /copilot/chat (REST) ─────────────────────────────────────────────────

@copilot_router.post(
    "/chat",
    response_model=CopilotChatResponse,
    summary="Send a message to the AI Copilot (REST)",
    description=(
        "Stateful copilot chat endpoint. "
        "Pass session_id from a previous response to continue a conversation. "
        "Rate-limited to 20 RPM per IP. "
        "For streaming/real-time, use the WebSocket endpoint instead."
    ),
)
async def copilot_chat(
    body: CopilotChatRequest,
    developer_id: Annotated[uuid.UUID | None, Depends(_get_developer_id)],
    db=Depends(get_async_session),
):
    async with db as session:
        # ── Get or create session ────────────────────────────────────────────
        copilot_session = await get_or_create_session(
            session,
            session_id=body.session_id,
            developer_id=developer_id,
        )

        # ── Load recent history for LangChain memory ─────────────────────────
        recent = await get_recent_messages(
            session, copilot_session.id, limit=settings.max_history_messages
        )
        history = [{"role": m.role.value, "content": m.content} for m in recent]

        # ── Persist user message ──────────────────────────────────────────────
        await append_message(
            session,
            session_id=copilot_session.id,
            role=MessageRole.user,
            content=body.message,
        )

        # ── Run agent turn ───────────────────────────────────────────────────
        reply, recommendation = await run_copilot_turn(
            user_message=body.message,
            history=history,
            settings=settings,
            listings_fetcher=_make_fetcher(session),
            recommendation_persister=_make_persister(session, developer_id),
        )

        # ── Persist assistant message ─────────────────────────────────────────
        rec_id = recommendation.recommendation_id if recommendation else None
        msg = await append_message(
            session,
            session_id=copilot_session.id,
            role=MessageRole.assistant,
            content=reply,
            router_recommendation_id=rec_id,
        )

        await session.commit()

        log.info(
            "copilot.chat.success",
            session_id=str(copilot_session.id),
            message_id=str(msg.id),
            has_recommendation=recommendation is not None,
        )

        return CopilotChatResponse(
            session_id=copilot_session.id,
            message_id=msg.id,
            content=reply,
            recommendation=recommendation,
        )


# ── WebSocket /copilot/ws/{session_id} ────────────────────────────────────────

@copilot_router.websocket("/ws/{session_id}")
async def copilot_ws(
    websocket: WebSocket,
    session_id: str,
    db=Depends(get_async_session),
):
    """
    WebSocket chat endpoint for the AI Copilot.

    Protocol:
      Client → sends: {"type": "chat", "session_id": "...", "message": "..."}
      Server → sends: {"type": "chat_response", "session_id": "...",
                        "content": "...", "recommendation": {...} | null}

    Session state is persisted to DB after each turn so the connection
    is fully stateless on the server side (compatible with horizontal scaling).
    """
    await websocket.accept()
    log.info("copilot.ws.connected", session_id=session_id)

    # Extract developer_id from Authorization header if present
    auth_header = websocket.headers.get("authorization", "")
    developer_id: uuid.UUID | None = None
    if auth_header.startswith("Bearer "):
        try:
            import jwt
            payload = jwt.decode(
                auth_header[7:],
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            developer_id = uuid.UUID(payload.get("sub")) if payload.get("sub") else None
        except Exception:
            pass

    try:
        async with db as session:
            ws_session_id = None
            try:
                ws_session_id = uuid.UUID(session_id)
            except ValueError:
                ws_session_id = None

            while True:
                raw = await websocket.receive_text()
                try:
                    data = WSInbound.model_validate_json(raw)
                except Exception as e:
                    await websocket.send_text(
                        WSOutbound(
                            type="error",
                            error=f"Invalid message format: {e}",
                        ).model_dump_json()
                    )
                    continue

                # Get or create session
                copilot_session = await get_or_create_session(
                    session,
                    session_id=ws_session_id,
                    developer_id=developer_id,
                )
                ws_session_id = copilot_session.id

                # Load history
                recent = await get_recent_messages(
                    session, copilot_session.id, limit=settings.max_history_messages
                )
                history = [{"role": m.role.value, "content": m.content} for m in recent]

                # Sanitize input
                user_message = data.message.strip()[:settings.max_input_length]

                # Persist user message
                await append_message(
                    session,
                    session_id=copilot_session.id,
                    role=MessageRole.user,
                    content=user_message,
                )

                # Run agent
                reply, recommendation = await run_copilot_turn(
                    user_message=user_message,
                    history=history,
                    settings=settings,
                    listings_fetcher=_make_fetcher(session),
                    recommendation_persister=_make_persister(session, developer_id),
                )

                # Persist assistant message
                rec_id = recommendation.recommendation_id if recommendation else None
                msg = await append_message(
                    session,
                    session_id=copilot_session.id,
                    role=MessageRole.assistant,
                    content=reply,
                    router_recommendation_id=rec_id,
                )

                await session.commit()

                # Send response
                outbound = WSOutbound(
                    type="chat_response",
                    session_id=str(copilot_session.id),
                    message_id=str(msg.id),
                    content=reply,
                    recommendation=(
                        recommendation.model_dump(mode="json") if recommendation else None
                    ),
                )
                await websocket.send_text(outbound.model_dump_json())

    except WebSocketDisconnect:
        log.info("copilot.ws.disconnected", session_id=session_id)
    except Exception as exc:
        log.error("copilot.ws.error", error=str(exc), session_id=session_id)
        try:
            await websocket.send_text(
                WSOutbound(type="error", error="Internal server error").model_dump_json()
            )
            await websocket.close()
        except Exception:
            pass


# ── GET /copilot/sessions/{id}/history ───────────────────────────────────────

@copilot_router.get(
    "/sessions/{session_id}/history",
    response_model=CopilotSessionHistory,
    summary="Fetch conversation history for a copilot session",
)
async def get_history(
    session_id: uuid.UUID,
    developer_id: Annotated[uuid.UUID | None, Depends(_get_developer_id)],
    db=Depends(get_async_session),
):
    async with db as session:
        copilot_session = await get_session_with_messages(session, session_id)
        if not copilot_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found.",
            )

        return CopilotSessionHistory(
            session_id=copilot_session.id,
            developer_id=copilot_session.developer_id,
            created_at=copilot_session.created_at.isoformat(),
            messages=[
                CopilotMessageOut(
                    id=m.id,
                    role=m.role.value,
                    content=m.content,
                    router_recommendation_id=m.router_recommendation_id,
                    created_at=m.created_at.isoformat(),
                )
                for m in copilot_session.messages
            ],
        )
