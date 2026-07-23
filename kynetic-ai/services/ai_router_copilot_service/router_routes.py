"""
AI Router & Copilot Service — Router Routes.

Endpoints:
  POST /router/recommend — budget/goal-based machine recommendation

Rate-limited: 30 RPM per IP (enforced at app middleware level; also
explicitly annotated here for documentation / gateway purposes).
"""

from __future__ import annotations

import json
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from libs.db_models.database import get_async_session
from services.ai_router_copilot_service.config import get_settings
from services.ai_router_copilot_service.ranking import rank_listings
from services.ai_router_copilot_service.repository import (
    fetch_active_listings,
    save_recommendation,
)
from services.ai_router_copilot_service.schemas import (
    RecommendRequest,
    RecommendResponse,
    ScoredListing,
)

log = structlog.get_logger(__name__)
settings = get_settings()

router_router = APIRouter(prefix="/router", tags=["router"])
bearer = HTTPBearer(auto_error=False)


def _get_developer_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> uuid.UUID | None:
    """
    Optionally extract developer_id from JWT for audit-trail purposes.
    Non-fatal: unauthenticated requests still get recommendations, but
    developer_id will be NULL in router_recommendations.
    """
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


@router_router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Get ranked machine recommendations",
    description=(
        "Submit a budget or goal (fastest/cheapest/balanced) and receive a ranked "
        "list of compute listings with estimated cost and runtime. "
        "Rate-limited to 30 RPM per IP."
    ),
)
async def recommend(
    body: RecommendRequest,
    request: Request,
    developer_id: Annotated[uuid.UUID | None, Depends(_get_developer_id)],
    db=Depends(get_async_session),
):
    async with db as session:
        # ── 1. Fetch candidate listings ──────────────────────────────────────
        listings = await fetch_active_listings(
            session,
            min_gpu_vram_gb=body.min_gpu_vram_gb,
            region=body.region,
        )

        if not listings:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No active listings found matching your filters. "
                    "Try relaxing budget, region, or VRAM requirements."
                ),
            )

        # ── 2. Extract budget constraints ────────────────────────────────────
        budget_usd: float | None = None
        budget_inr: float | None = None
        if body.budget:
            if body.budget.currency == "usd":
                budget_usd = float(body.budget.amount)
            else:
                budget_inr = float(body.budget.amount)

        # ── 3. Rank ──────────────────────────────────────────────────────────
        ranked: list[ScoredListing] = rank_listings(
            listings,
            goal=body.goal,
            budget_usd=budget_usd,
            budget_inr=budget_inr,
            weight_price=settings.weight_price,
            weight_benchmark=settings.weight_benchmark,
            weight_availability=settings.weight_availability,
        )

        if not ranked:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    "No listings match your budget. "
                    "All candidates exceed the specified ceiling. "
                    "Try increasing the budget or switching currency."
                ),
            )

        # ── 4. Persist audit record ──────────────────────────────────────────
        ranked_dicts = [r.model_dump(mode="json") for r in ranked]
        rec = await save_recommendation(
            session,
            developer_id=developer_id,
            request_payload=body.model_dump(mode="json"),
            recommended_listing_ids=[str(r.listing_id) for r in ranked],
            ranked_results=ranked_dicts,
        )
        await session.commit()

        log.info(
            "router.recommend.success",
            recommendation_id=str(rec.id),
            developer_id=str(developer_id),
            goal=body.goal,
            budget_usd=budget_usd,
            results=len(ranked),
        )

        return RecommendResponse(
            recommendation_id=rec.id,
            request=body.model_dump(mode="json"),
            results=ranked,
            total_candidates_evaluated=len(listings),
        )
