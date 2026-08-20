"""
Notifications Service — API routes.

Endpoints:
  GET  /notifications                  list notifications (with unread count)
  POST /notifications/{id}/read        mark one notification as read
  POST /notifications/mark-all-read    mark all as read
  GET  /notifications/preferences      get notification preferences
  PUT  /notifications/preferences      update preferences
  POST /support/tickets                create support ticket
  GET  /support/tickets                list user's support tickets
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common.auth import require_auth
from libs.db_models.database import get_db_session
from services.notifications_service.repository import (
    NotificationPreferenceRepository,
    NotificationRepository,
    SupportTicketRepository,
)
from services.wallet_billing_service.schemas import (
    NotificationListResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationResponse,
    SupportTicketCreate,
    SupportTicketResponse,
)

logger = structlog.get_logger(__name__)

notifications_router = APIRouter(prefix="/notifications", tags=["Notifications"])
support_router = APIRouter(prefix="/support", tags=["Support"])


# ── GET /notifications ─────────────────────────────────────────────────────

@notifications_router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List all notifications for the authenticated user."""
    user_id = uuid.UUID(auth["sub"])
    repo = NotificationRepository(session)
    items, total, unread = await repo.get_for_user(
        user_id, page=page, page_size=page_size, unread_only=unread_only
    )
    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in items],
        total=total,
        unread_count=unread,
        page=page,
        page_size=page_size,
    )


# ── POST /notifications/{id}/read ─────────────────────────────────────────

@notifications_router.post("/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_notification_read(
    notification_id: uuid.UUID,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Mark a single notification as read."""
    user_id = uuid.UUID(auth["sub"])
    repo = NotificationRepository(session)
    await repo.mark_read(notification_id, user_id)
    await session.commit()


# ── POST /notifications/mark-all-read ─────────────────────────────────────

@notifications_router.post("/mark-all-read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_notifications_read(
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Mark all of the user's notifications as read."""
    user_id = uuid.UUID(auth["sub"])
    repo = NotificationRepository(session)
    await repo.mark_all_read(user_id)
    await session.commit()


# ── GET /notifications/preferences ────────────────────────────────────────

@notifications_router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_notification_preferences(
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Get notification preferences for the authenticated user."""
    user_id = uuid.UUID(auth["sub"])
    pref_repo = NotificationPreferenceRepository(session)
    pref = await pref_repo.get_or_create(user_id)
    await session.commit()
    return NotificationPreferenceResponse.model_validate(pref)


# ── PUT /notifications/preferences ────────────────────────────────────────

@notifications_router.put("/preferences", response_model=NotificationPreferenceResponse)
async def update_notification_preferences(
    body: NotificationPreferenceUpdate,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """Update notification preferences for the authenticated user."""
    user_id = uuid.UUID(auth["sub"])
    pref_repo = NotificationPreferenceRepository(session)
    pref = await pref_repo.update(
        user_id,
        email_enabled=body.email_enabled,
        sms_enabled=body.sms_enabled,
        low_balance_threshold_usd=body.low_balance_threshold_usd,
    )
    await session.commit()
    return NotificationPreferenceResponse.model_validate(pref)


# ── POST /support/tickets ──────────────────────────────────────────────────

@support_router.post("/tickets", response_model=SupportTicketResponse, status_code=status.HTTP_201_CREATED)
async def create_support_ticket(
    body: SupportTicketCreate,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Create a support ticket.
    Tickets flagged with region='india' are routed to the India support channel.
    """
    user_id = uuid.UUID(auth["sub"])
    repo = SupportTicketRepository(session)
    ticket = await repo.create(
        user_id=user_id,
        subject=body.subject,
        region=body.region,
    )
    await session.commit()
    logger.info(
        "support_ticket_created",
        ticket_id=str(ticket.id),
        region=body.region,
        user_id=str(user_id),
    )
    return SupportTicketResponse.model_validate(ticket)


# ── GET /support/tickets ───────────────────────────────────────────────────

@support_router.get("/tickets", response_model=list[SupportTicketResponse])
async def list_support_tickets(
    page: int = 1,
    page_size: int = 20,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """List support tickets for the authenticated user."""
    user_id = uuid.UUID(auth["sub"])
    repo = SupportTicketRepository(session)
    tickets, _total = await repo.get_for_user(user_id, page=page, page_size=page_size)
    return [SupportTicketResponse.model_validate(t) for t in tickets]
