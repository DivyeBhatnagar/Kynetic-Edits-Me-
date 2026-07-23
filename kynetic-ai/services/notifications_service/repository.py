"""
Notifications Service — Repository.

Handles DB operations for Notification, NotificationPreference, SupportTicket.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.billing_monitoring_models import (
    Notification,
    NotificationChannel,
    NotificationPreference,
    NotificationType,
    SupportRegion,
    SupportTicket,
    SupportTicketStatus,
)


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        notification_type: NotificationType,
        title: str,
        body: str,
        channel: NotificationChannel = NotificationChannel.in_app,
        payload: dict | None = None,
    ) -> Notification:
        notif = Notification(
            id=uuid.uuid4(),
            user_id=user_id,
            notification_type=notification_type,
            channel=channel,
            title=title,
            body=body,
            payload=payload,
        )
        self._session.add(notif)
        return notif

    async def get_for_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        unread_only: bool = False,
    ) -> tuple[list[Notification], int, int]:
        """Returns (items, total_count, unread_count)."""
        base_q = select(Notification).where(Notification.user_id == user_id)
        if unread_only:
            base_q = base_q.where(Notification.is_read.is_(False))

        total_result = await self._session.execute(
            select(func.count()).select_from(
                select(Notification).where(Notification.user_id == user_id).subquery()
            )
        )
        total = total_result.scalar_one()

        unread_result = await self._session.execute(
            select(func.count()).select_from(
                select(Notification)
                .where(Notification.user_id == user_id)
                .where(Notification.is_read.is_(False))
                .subquery()
            )
        )
        unread = unread_result.scalar_one()

        items_result = await self._session.execute(
            base_q
            .order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list(items_result.scalars().all())
        return items, total, unread

    async def mark_read(self, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .where(Notification.user_id == user_id)
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self._session.execute(
            update(Notification)
            .where(Notification.user_id == user_id)
            .where(Notification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(timezone.utc))
        )

    async def mark_sent(self, notification_id: uuid.UUID) -> None:
        await self._session.execute(
            update(Notification)
            .where(Notification.id == notification_id)
            .values(sent_at=datetime.now(timezone.utc))
        )


class NotificationPreferenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, user_id: uuid.UUID) -> NotificationPreference:
        result = await self._session.execute(
            select(NotificationPreference).where(NotificationPreference.user_id == user_id)
        )
        pref = result.scalar_one_or_none()
        if pref is None:
            pref = NotificationPreference(id=uuid.uuid4(), user_id=user_id)
            self._session.add(pref)
        return pref

    async def update(
        self,
        user_id: uuid.UUID,
        *,
        email_enabled: bool | None = None,
        sms_enabled: bool | None = None,
        low_balance_threshold_usd: str | None = None,
    ) -> NotificationPreference:
        pref = await self.get_or_create(user_id)
        if email_enabled is not None:
            pref.email_enabled = email_enabled
        if sms_enabled is not None:
            pref.sms_enabled = sms_enabled
        if low_balance_threshold_usd is not None:
            pref.low_balance_threshold_usd = low_balance_threshold_usd
        return pref


class SupportTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: uuid.UUID,
        subject: str,
        region: str = "global",
        external_ticket_id: str | None = None,
    ) -> SupportTicket:
        _region = SupportRegion.india if region == "india" else SupportRegion.global_
        ticket = SupportTicket(
            id=uuid.uuid4(),
            user_id=user_id,
            region=_region,
            subject=subject,
            status=SupportTicketStatus.open,
            external_ticket_id=external_ticket_id,
        )
        self._session.add(ticket)
        return ticket

    async def get_for_user(
        self,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[SupportTicket], int]:
        total_result = await self._session.execute(
            select(func.count()).select_from(
                select(SupportTicket).where(SupportTicket.user_id == user_id).subquery()
            )
        )
        total = total_result.scalar_one()

        items_result = await self._session.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user_id)
            .order_by(SupportTicket.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(items_result.scalars().all()), total
