"""
Security Service — Platform Emergency Kill Switch Engine (kill_switch.py)

Instantly revokes instances, host registrations, or user accounts when security anomalies or abuse are detected (§14).
"""

import uuid
import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.provisioning_models import Instance, InstanceStatus
from libs.db_models.host_models import Host, HostStatus
from libs.db_models.user_models import User
from libs.db_models.security_models import KillSwitchEvent

log = structlog.get_logger(__name__)


async def trigger_emergency_kill_switch(
    target_type: str,  # 'instance' | 'host' | 'user'
    target_id: uuid.UUID,
    reason: str,
    session: AsyncSession,
) -> KillSwitchEvent:
    """
    Triggers immediate emergency revocation across Control Plane.
    """
    log.error("security.kill_switch_triggered", target_type=target_type, target_id=str(target_id), reason=reason)

    if target_type == "instance":
        await session.execute(
            update(Instance)
            .where(Instance.id == target_id)
            .values(status=InstanceStatus.terminated, hold_released=True)
        )
    elif target_type == "host":
        await session.execute(
            update(Host)
            .where(Host.id == target_id)
            .values(status=HostStatus.SUSPENDED, flagged_reason=reason)
        )
        await session.execute(
            update(Instance)
            .where(Instance.host_id == target_id)
            .values(status=InstanceStatus.terminated, hold_released=True)
        )
    elif target_type == "user":
        await session.execute(
            update(User)
            .where(User.id == target_id)
            .values(is_active=False)
        )
        await session.execute(
            update(Instance)
            .where(Instance.developer_id == target_id)
            .values(status=InstanceStatus.terminated, hold_released=True)
        )

    from libs.db_models.security_models import KillSwitchTargetType

    event = KillSwitchEvent(
        id=uuid.uuid4(),
        target_type=KillSwitchTargetType(target_type),
        target_id=str(target_id),
        reason=reason,
    )
    session.add(event)
    await session.flush()
    return event
