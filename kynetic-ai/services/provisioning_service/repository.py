"""
Provisioning Service — Repository.

Async SQLAlchemy CRUD for instances, ssh_sessions, secure_deletion_receipts.

CRITICAL: All instance status changes must go through
`InstanceRepository.transition_state()` which enforces the legal
state machine transitions. Never set instance.status directly.
"""

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.provisioning_models import (
    Instance,
    InstanceStatus,
    SSHSession,
    SecureDeletionReceipt,
)

# ── Legal state transitions ────────────────────────────────────────────────
# Maps current_status → set of valid next statuses
LEGAL_TRANSITIONS: dict[InstanceStatus, set[InstanceStatus]] = {
    InstanceStatus.pending:       {InstanceStatus.provisioning, InstanceStatus.failed, InstanceStatus.terminated},
    InstanceStatus.provisioning:  {InstanceStatus.running,     InstanceStatus.failed, InstanceStatus.terminated},
    InstanceStatus.running:       {InstanceStatus.stopping,    InstanceStatus.failed, InstanceStatus.terminated},
    InstanceStatus.stopping:      {InstanceStatus.stopped,     InstanceStatus.failed, InstanceStatus.terminated},
    InstanceStatus.stopped:       {InstanceStatus.running,     InstanceStatus.terminated},
    # Terminal states — no further transitions
    InstanceStatus.terminated:    set(),
    InstanceStatus.failed:        {InstanceStatus.terminated},  # Allow cleanup
}


class IllegalTransitionError(Exception):
    def __init__(self, current: InstanceStatus, requested: InstanceStatus):
        super().__init__(
            f"Illegal instance state transition: {current.value} → {requested.value}"
        )
        self.current = current
        self.requested = requested


class InstanceRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    # ── Create ─────────────────────────────────────────────────────────────

    async def create(
        self,
        *,
        developer_id: uuid.UUID,
        listing_id: uuid.UUID,
        host_id: uuid.UUID,
        hold_amount: Decimal,
        price_per_second_usd: Decimal,
        agent_host_url: str,
        public_ip: str | None = None,
        ssh_port: int = 22,
        template_id: uuid.UUID | None = None,
    ) -> Instance:
        instance = Instance(
            id=uuid.uuid4(),
            developer_id=developer_id,
            listing_id=listing_id,
            host_id=host_id,
            status=InstanceStatus.pending,
            hold_amount=hold_amount,
            price_per_second_usd=price_per_second_usd,
            agent_host_url=agent_host_url,
            public_ip=public_ip,
            ssh_port=ssh_port,
            billed_seconds=0,
            hold_released=False,
            template_id=template_id,
        )
        self._session.add(instance)
        await self._session.flush()
        return instance

    # ── Read ───────────────────────────────────────────────────────────────

    async def get_by_id(self, instance_id: uuid.UUID) -> Instance | None:
        result = await self._session.execute(
            select(Instance).where(Instance.id == instance_id)
        )
        return result.scalar_one_or_none()

    async def get_by_developer(
        self,
        developer_id: uuid.UUID,
        *,
        status: InstanceStatus | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Instance], int]:
        q = select(Instance).where(Instance.developer_id == developer_id)
        if status:
            q = q.where(Instance.status == status)
        q_count = select(Instance).where(Instance.developer_id == developer_id)
        if status:
            q_count = q_count.where(Instance.status == status)

        from sqlalchemy import func
        count_result = await self._session.execute(
            select(func.count()).select_from(q_count.subquery())
        )
        total = count_result.scalar_one()

        q = q.order_by(Instance.created_at.desc())
        q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self._session.execute(q)
        return result.scalars().all(), total

    async def get_all_running(self) -> list[Instance]:
        """Returns all currently running instances (billing watcher uses this)."""
        result = await self._session.execute(
            select(Instance).where(Instance.status == InstanceStatus.running)
        )
        return list(result.scalars().all())

    # ── State machine ───────────────────────────────────────────────────────

    async def transition_state(
        self,
        instance_id: uuid.UUID,
        new_status: InstanceStatus,
        *,
        firecracker_vm_id: str | None = None,
        container_id: str | None = None,
        wireguard_ip: str | None = None,
    ) -> Instance:
        """
        Atomically transitions an instance to a new state.
        Raises IllegalTransitionError if the transition is not permitted.
        """
        instance = await self.get_by_id(instance_id)
        if instance is None:
            raise ValueError(f"Instance {instance_id} not found")

        allowed = LEGAL_TRANSITIONS.get(instance.status, set())
        if new_status not in allowed:
            raise IllegalTransitionError(instance.status, new_status)

        instance.status = new_status

        # Side-effects on specific transitions
        now = datetime.now(tz=timezone.utc)
        if new_status == InstanceStatus.running:
            if instance.started_at is None:
                instance.started_at = now
            if firecracker_vm_id:
                instance.firecracker_vm_id = firecracker_vm_id
            if container_id:
                instance.container_id = container_id
            if wireguard_ip:
                instance.wireguard_ip = wireguard_ip

        elif new_status == InstanceStatus.stopping:
            instance.stopped_at = now

        elif new_status == InstanceStatus.terminated:
            instance.terminated_at = now

        await self._session.flush()
        return instance

    # ── Billing ────────────────────────────────────────────────────────────

    async def increment_billed_seconds(
        self, instance_id: uuid.UUID, seconds: int = 1
    ) -> None:
        """Fast UPDATE for billing ticker — avoids SELECT round-trip."""
        await self._session.execute(
            update(Instance)
            .where(Instance.id == instance_id)
            .values(billed_seconds=Instance.billed_seconds + seconds)
        )

    async def release_hold(self, instance_id: uuid.UUID) -> None:
        await self._session.execute(
            update(Instance)
            .where(Instance.id == instance_id)
            .values(hold_released=True)
        )


class SSHSessionRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        instance_id: uuid.UUID,
        public_key: str,
        private_key_encrypted: str,
        relay_host: str | None = None,
        relay_port: int | None = None,
    ) -> SSHSession:
        ssh_session = SSHSession(
            id=uuid.uuid4(),
            instance_id=instance_id,
            public_key=public_key,
            private_key_encrypted=private_key_encrypted,
            relay_host=relay_host,
            relay_port=relay_port,
        )
        self._session.add(ssh_session)
        await self._session.flush()
        return ssh_session

    async def get_by_instance(self, instance_id: uuid.UUID) -> SSHSession | None:
        result = await self._session.execute(
            select(SSHSession).where(SSHSession.instance_id == instance_id)
        )
        return result.scalar_one_or_none()

    async def revoke(self, instance_id: uuid.UUID) -> None:
        """
        Null out the encrypted private key on termination.
        The plaintext is unrecoverable after this point.
        """
        now = datetime.now(tz=timezone.utc)
        await self._session.execute(
            update(SSHSession)
            .where(SSHSession.instance_id == instance_id)
            .values(private_key_encrypted=None, revoked_at=now)
        )


class SecureDeletionRepository:

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        *,
        instance_id: uuid.UUID,
        method: str,
        agent_confirmation_hash: str,
        agent_payload: str | None = None,
    ) -> SecureDeletionReceipt:
        """Immutable write — no update/delete methods exist."""
        receipt = SecureDeletionReceipt(
            id=uuid.uuid4(),
            instance_id=instance_id,
            method=method,
            agent_confirmation_hash=agent_confirmation_hash,
            agent_payload=agent_payload,
        )
        self._session.add(receipt)
        await self._session.flush()
        return receipt

    async def get_by_instance(
        self, instance_id: uuid.UUID
    ) -> SecureDeletionReceipt | None:
        result = await self._session.execute(
            select(SecureDeletionReceipt).where(
                SecureDeletionReceipt.instance_id == instance_id
            )
        )
        return result.scalar_one_or_none()
