"""
Shared Audit Logger — libs/common/audit.py

A thin helper that every service uses to write to security_event_logs.
This ensures all services emit audit events in a consistent format without
needing to duplicate the ORM session / repository boilerplate.

Usage (from any async FastAPI route or Celery task):
    from libs.common.audit import audit_log, AuditContext

    await audit_log(
        session=db_session,
        event_type=SecurityEventType.login_success,
        user_id=user.id,
        ip_address=request.client.host,
        details={"method": "email"},
    )
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.security_models import (
    SecurityEventLog,
    SecurityEventSeverity,
    SecurityEventType,
)


async def audit_log(
    session: AsyncSession,
    event_type: SecurityEventType,
    *,
    severity: SecurityEventSeverity = SecurityEventSeverity.info,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    ip_address: str | None = None,
    details: dict[str, Any] | None = None,
) -> SecurityEventLog:
    """
    Writes an immutable audit event to security_event_logs.
    The session is flushed (not committed) — commit is the caller's responsibility.

    NEVER raises — if the write fails, we log the failure but do not interrupt
    the primary operation. Audit failures are serious but must not block users.
    """
    import structlog
    log = structlog.get_logger(__name__)

    try:
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
        session.add(ev)
        await session.flush()
        return ev
    except Exception as exc:
        log.error(
            "audit_log.write_failed",
            event_type=event_type.value,
            user_id=str(user_id) if user_id else None,
            error=str(exc),
        )
        # Return a dummy object so callers don't have to null-check
        return SecurityEventLog(
            id=uuid.uuid4(),
            event_type=event_type,
            severity=severity,
        )
