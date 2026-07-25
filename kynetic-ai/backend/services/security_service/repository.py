"""
Security Service — Repository.

CRUD for all security-related tables.
Rules:
  - SecurityEventLog and KillSwitchEvent are append-only — no update/delete methods.
  - TrustTier is upserted (one row per user).
  - DeviceFingerprint is upserted (one row per user×hash pair).
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.security_models import (
    DeviceFingerprint,
    KillSwitchEvent,
    KillSwitchTargetType,
    SecurityEventLog,
    SecurityEventSeverity,
    SecurityEventType,
    TrustTier,
    TrustTierLevel,
)


class SecurityEventRepository:
    """Append-only security event log."""

    def __init__(self, session: AsyncSession):
        self._s = session

    async def log(
        self,
        event_type: SecurityEventType,
        severity: SecurityEventSeverity = SecurityEventSeverity.info,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        user_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> SecurityEventLog:
        ev = SecurityEventLog(
            id=uuid.uuid4(),
            event_type=event_type,
            severity=severity,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            user_id=user_id,
            ip_address=ip_address,
            details=details,
        )
        self._s.add(ev)
        await self._s.flush()
        return ev

    async def list(
        self,
        *,
        severity: SecurityEventSeverity | None = None,
        event_type: SecurityEventType | None = None,
        user_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[SecurityEventLog], int]:
        q = select(SecurityEventLog)
        if severity:
            q = q.where(SecurityEventLog.severity == severity)
        if event_type:
            q = q.where(SecurityEventLog.event_type == event_type)
        if user_id:
            q = q.where(SecurityEventLog.user_id == user_id)

        count_q = select(func.count()).select_from(q.subquery())
        total = (await self._s.execute(count_q)).scalar_one()

        q = q.order_by(SecurityEventLog.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        rows = (await self._s.execute(q)).scalars().all()
        return list(rows), total


class KillSwitchRepository:
    """Append-only kill-switch event log."""

    def __init__(self, session: AsyncSession):
        self._s = session

    async def create(
        self,
        *,
        target_type: KillSwitchTargetType,
        target_id: str,
        triggered_by: uuid.UUID | None,
        reason: str | None,
        broadcast_result: dict[str, Any] | None = None,
    ) -> KillSwitchEvent:
        ev = KillSwitchEvent(
            id=uuid.uuid4(),
            target_type=target_type,
            target_id=target_id,
            triggered_by=triggered_by,
            reason=reason,
            broadcast_result=broadcast_result,
        )
        self._s.add(ev)
        await self._s.flush()
        return ev


class TrustTierRepository:
    """One-row-per-user trust tier management."""

    def __init__(self, session: AsyncSession):
        self._s = session

    async def get(self, user_id: uuid.UUID) -> TrustTier | None:
        result = await self._s.execute(
            select(TrustTier).where(TrustTier.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create_default(self, user_id: uuid.UUID) -> TrustTier:
        tier = await self.get(user_id)
        if tier:
            return tier
        tier = TrustTier(
            id=uuid.uuid4(),
            user_id=user_id,
            tier=TrustTierLevel.unverified,
        )
        self._s.add(tier)
        await self._s.flush()
        return tier

    async def update(
        self,
        user_id: uuid.UUID,
        *,
        tier: TrustTierLevel | None = None,
        max_instance_vcpus: int | None = ...,
        max_gpu_vram_gb: int | None = ...,
        max_gpu_hours_month: int | None = ...,
        max_spend_usd_month: float | None = ...,
        is_wallet_frozen: bool | None = None,
    ) -> TrustTier:
        """Upsert trust tier — creates default record if missing."""
        record = await self.get_or_create_default(user_id)
        if tier is not None:
            record.tier = tier
        if max_instance_vcpus is not ...:
            record.max_instance_vcpus = max_instance_vcpus
        if max_gpu_vram_gb is not ...:
            record.max_gpu_vram_gb = max_gpu_vram_gb
        if max_gpu_hours_month is not ...:
            record.max_gpu_hours_month = max_gpu_hours_month
        if max_spend_usd_month is not ...:
            record.max_spend_usd_month = max_spend_usd_month
        if is_wallet_frozen is not None:
            record.is_wallet_frozen = is_wallet_frozen
        record.updated_at = datetime.now(tz=timezone.utc)
        await self._s.flush()
        return record

    async def freeze_wallet(self, user_id: uuid.UUID) -> TrustTier:
        return await self.update(user_id, is_wallet_frozen=True)

    async def unfreeze_wallet(self, user_id: uuid.UUID) -> TrustTier:
        return await self.update(user_id, is_wallet_frozen=False)


class DeviceFingerprintRepository:

    def __init__(self, session: AsyncSession):
        self._s = session

    async def upsert(
        self,
        user_id: uuid.UUID,
        fingerprint_hash: str,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[DeviceFingerprint, bool]:
        """
        Upsert the fingerprint for this user×hash pair.
        Returns (record, is_new).
        """
        existing = await self._s.execute(
            select(DeviceFingerprint).where(
                DeviceFingerprint.user_id == user_id,
                DeviceFingerprint.fingerprint_hash == fingerprint_hash,
            )
        )
        record = existing.scalar_one_or_none()
        if record:
            record.seen_count += 1
            record.last_seen = datetime.now(tz=timezone.utc)
            if ip_address:
                record.ip_address = ip_address
            await self._s.flush()
            return record, False

        record = DeviceFingerprint(
            id=uuid.uuid4(),
            user_id=user_id,
            fingerprint_hash=fingerprint_hash,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._s.add(record)
        await self._s.flush()
        return record, True

    async def count_users_with_fingerprint(self, fingerprint_hash: str) -> int:
        """
        Returns how many distinct users have been seen with this fingerprint.
        > 1 → multi-account suspected.
        """
        result = await self._s.execute(
            select(func.count(func.distinct(DeviceFingerprint.user_id))).where(
                DeviceFingerprint.fingerprint_hash == fingerprint_hash
            )
        )
        return result.scalar_one()
