"""
Phase 31 — Instance Audit Logger (services/provisioning_service/audit.py)

Logs instance lifecycle events (create, start, stop, terminate, failed) and
validation rejections (INSUFFICIENT_BALANCE, PERMISSION_DENIED, etc.) to both:
  1. Centralized structlog stream (tagged by instance_id, actor_id, action)
  2. Database `audit_logs` table (immutable audit trail)

Design:
  - Fail-safe execution: audit log failure will NOT raise or block the core flow.
  - Converts string/UUID actor_id and instance_id into safe database records.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import AuditLog

logger = structlog.get_logger("provisioning.audit")


async def log_instance_event(
    db: AsyncSession,
    *,
    actor_id: str | uuid.UUID,
    instance_id: str | uuid.UUID,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """
    Log an instance event to structlog and persist an AuditLog row in DB.

    Args:
        db:          Active AsyncSession
        actor_id:    User ID triggering the event (UUID or string)
        instance_id: Target instance ID
        action:      Event action (e.g. 'create', 'start', 'stop', 'terminate', 'failed', 'validation_rejected')
        metadata:    Context data dict (error details, initial parameters, etc.)
    """
    meta = metadata or {}
    actor_str = str(actor_id)
    inst_str = str(instance_id)

    # 1. Structured logging
    logger.info(
        "instance_event",
        instance_id=inst_str,
        action=action,
        actor_id=actor_str,
        **meta,
    )

    # 2. Database audit logging (fail-safe)
    try:
        actor_uuid = None
        try:
            actor_uuid = uuid.UUID(actor_str)
        except ValueError:
            pass

        audit_entry = AuditLog(
            id=uuid.uuid4(),
            actor_id=actor_uuid,
            action=action,
            resource_type="instance",
            resource_id=inst_str,
            extra_data=meta,
        )
        db.add(audit_entry)
        await db.flush()
    except Exception as exc:
        logger.error(
            "instance_event.db_log_failed",
            instance_id=inst_str,
            action=action,
            error=str(exc),
        )


async def log_validation_rejection(
    db: AsyncSession,
    *,
    requester_id: str | uuid.UUID,
    instance_id: str | uuid.UUID | None = None,
    listing_id: str | uuid.UUID | None = None,
    code: str,
    message: str,
) -> None:
    """
    Log a business logic validation rejection (Phase 27 gate failure).
    Useful for security auditing and fraud signal mining.
    """
    meta = {
        "code": code,
        "message": message,
        "listing_id": str(listing_id) if listing_id else None,
    }
    await log_instance_event(
        db,
        actor_id=requester_id,
        instance_id=instance_id or listing_id or "unassigned",
        action="validation_rejected",
        metadata=meta,
    )
