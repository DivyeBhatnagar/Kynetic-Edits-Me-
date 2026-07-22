"""
Host Service — Repository layer.

All DB access for host-related operations.
Every mutation emits an audit log entry through AuditLogRepository.
"""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from libs.db_models.host_models import (
    BenchmarkType,
    Host,
    HostBenchmark,
    HostHeartbeat,
    HostHardwareSpec,
    HostStatus,
    HeartbeatStatus,
)
from libs.db_models.models import AuditLog
from services.host_service.schemas import (
    BenchmarkResultSchema,
    HardwareSpecSchema,
    HeartbeatRequest,
    OSType,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Audit log helper (reused from auth service pattern)
# ---------------------------------------------------------------------------
class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        action: str,
        actor_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            metadata=metadata,
        )
        self.session.add(log)
        await self.session.flush()
        return log


# ---------------------------------------------------------------------------
# Host Repository
# ---------------------------------------------------------------------------
class HostRepository:
    def __init__(self, session: AsyncSession, audit_repo: AuditLogRepository) -> None:
        self.session = session
        self.audit = audit_repo

    async def create(
        self,
        user_id: uuid.UUID,
        os_type: OSType,
        agent_version: str,
        mtls_cert_fingerprint: str | None = None,
    ) -> Host:
        host = Host(
            user_id=user_id,
            os_type=os_type,
            agent_version=agent_version,
            mtls_cert_fingerprint=mtls_cert_fingerprint,
            status=HostStatus.PENDING_VERIFICATION,
        )
        self.session.add(host)
        await self.session.flush()

        await self.audit.create(
            action="host.registered",
            actor_id=user_id,
            resource_type="host",
            resource_id=str(host.id),
            metadata={"os_type": os_type, "agent_version": agent_version},
        )
        logger.info("host_created", host_id=str(host.id), user_id=str(user_id))
        return host

    async def get_by_id(self, host_id: uuid.UUID) -> Host | None:
        result = await self.session.execute(
            select(Host)
            .where(Host.id == host_id)
            .options(selectinload(Host.hardware_specs))
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: uuid.UUID) -> list[Host]:
        result = await self.session.execute(
            select(Host).where(Host.user_id == user_id).order_by(Host.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_cert_fingerprint(self, fingerprint: str) -> Host | None:
        result = await self.session.execute(
            select(Host).where(Host.mtls_cert_fingerprint == fingerprint)
        )
        return result.scalar_one_or_none()

    async def set_status(
        self,
        host_id: uuid.UUID,
        status: HostStatus,
        actor_id: uuid.UUID | None = None,
        reason: str | None = None,
    ) -> None:
        values: dict = {"status": status, "updated_at": datetime.now(UTC)}
        if reason is not None:
            values["flagged_reason"] = reason
        await self.session.execute(
            update(Host).where(Host.id == host_id).values(**values)
        )
        await self.audit.create(
            action=f"host.status_changed.{status.value}",
            actor_id=actor_id,
            resource_type="host",
            resource_id=str(host_id),
            metadata={"new_status": status.value, "reason": reason},
        )

    async def mark_spec_verified(self, host_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Host)
            .where(Host.id == host_id)
            .values(spec_verified=True, updated_at=datetime.now(UTC))
        )

    async def mark_benchmark_verified(self, host_id: uuid.UUID) -> None:
        await self.session.execute(
            update(Host)
            .where(Host.id == host_id)
            .values(
                benchmark_verified=True,
                status=HostStatus.VERIFIED,
                updated_at=datetime.now(UTC),
            )
        )
        await self.audit.create(
            action="host.verification_complete",
            resource_type="host",
            resource_id=str(host_id),
        )

    async def get_hosts_needing_rebenchmark(
        self, interval_hours: int
    ) -> list[Host]:
        """Return verified hosts whose last benchmark is older than interval_hours."""
        cutoff = datetime.now(UTC) - timedelta(hours=interval_hours)
        # Subquery: last benchmark run per host
        from sqlalchemy import func
        last_run_sq = (
            select(
                HostBenchmark.host_id,
                func.max(HostBenchmark.run_at).label("last_run")
            )
            .group_by(HostBenchmark.host_id)
            .subquery()
        )
        result = await self.session.execute(
            select(Host)
            .join(last_run_sq, Host.id == last_run_sq.c.host_id, isouter=True)
            .where(
                Host.status.in_([HostStatus.VERIFIED, HostStatus.LISTED]),
                (last_run_sq.c.last_run == None) | (last_run_sq.c.last_run < cutoff),  # noqa: E711
            )
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Hardware Spec Repository
# ---------------------------------------------------------------------------
class HardwareSpecRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, host_id: uuid.UUID, spec: HardwareSpecSchema) -> HostHardwareSpec:
        record = HostHardwareSpec(
            host_id=host_id,
            cpu_model=spec.cpu_model,
            cpu_cores=spec.cpu_cores,
            cpu_threads=spec.cpu_threads,
            ram_gb=spec.ram_gb,
            disk_type=spec.disk_type,
            disk_gb=spec.disk_gb,
            gpu_model=spec.gpu_model,
            gpu_count=spec.gpu_count,
            gpu_vram_gb=spec.gpu_vram_gb,
            driver_version=spec.driver_version,
            cuda_version=spec.cuda_version,
            temperature_c=spec.temperature_c,
            power_draw_w=spec.power_draw_w,
            raw_spec=spec.raw_spec,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def get_latest(self, host_id: uuid.UUID) -> HostHardwareSpec | None:
        result = await self.session.execute(
            select(HostHardwareSpec)
            .where(HostHardwareSpec.host_id == host_id)
            .order_by(HostHardwareSpec.reported_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Benchmark Repository
# ---------------------------------------------------------------------------
class BenchmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_many(
        self,
        host_id: uuid.UUID,
        results: list[BenchmarkResultSchema],
        is_rerun: bool = False,
    ) -> list[HostBenchmark]:
        records = [
            HostBenchmark(
                host_id=host_id,
                benchmark_type=r.benchmark_type,
                score=r.score,
                raw_metrics=r.raw_metrics,
                is_rerun=is_rerun,
            )
            for r in results
        ]
        self.session.add_all(records)
        await self.session.flush()
        logger.info(
            "benchmarks_stored",
            host_id=str(host_id),
            count=len(records),
            is_rerun=is_rerun,
        )
        return records

    async def get_by_host(self, host_id: uuid.UUID) -> list[HostBenchmark]:
        result = await self.session.execute(
            select(HostBenchmark)
            .where(HostBenchmark.host_id == host_id)
            .order_by(HostBenchmark.run_at.desc())
        )
        return list(result.scalars().all())

    async def get_latest_by_type(
        self, host_id: uuid.UUID, benchmark_type: BenchmarkType
    ) -> HostBenchmark | None:
        result = await self.session.execute(
            select(HostBenchmark)
            .where(
                HostBenchmark.host_id == host_id,
                HostBenchmark.benchmark_type == benchmark_type,
            )
            .order_by(HostBenchmark.run_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Heartbeat Repository
# ---------------------------------------------------------------------------
class HeartbeatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, req: HeartbeatRequest) -> HostHeartbeat:
        hb = HostHeartbeat(
            host_id=req.host_id,
            status=req.status,
            temperature_c=req.temperature_c,
            power_draw_w=req.power_draw_w,
            gpu_utilization_pct=req.gpu_utilization_pct,
            ram_used_gb=req.ram_used_gb,
        )
        self.session.add(hb)
        await self.session.flush()
        return hb

    async def get_latest(self, host_id: uuid.UUID) -> HostHeartbeat | None:
        result = await self.session.execute(
            select(HostHeartbeat)
            .where(HostHeartbeat.host_id == host_id)
            .order_by(HostHeartbeat.recorded_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
