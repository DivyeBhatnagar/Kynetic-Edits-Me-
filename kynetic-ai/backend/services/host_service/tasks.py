"""
Host Service — Celery tasks.

All tasks are idempotent and safe to retry on transient failures.
Database operations use synchronous SQLAlchemy (not async) because
Celery workers run in a synchronous event loop.

Tasks:
- process_heartbeat        — Store heartbeat, update host last-seen status
- trigger_rebenchmark      — Send a re-benchmark command to a host (via Redis pub/sub)
- rebenchmark_sweep        — Periodic: find stale hosts, enqueue trigger_rebenchmark
- mark_offline_sweep       — Periodic: find silent hosts, mark them offline
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from celery.utils.log import get_task_logger
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker

from libs.db_models.host_models import Host, HostHeartbeat, HostStatus, HeartbeatStatus
from services.host_service.celery_app import celery_app
from services.host_service.config import get_settings

logger = get_task_logger(__name__)
settings = get_settings()

_SYNC_DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://kynetic:kynetic@localhost:5432/kynetic",
).replace("+asyncpg", "").replace("+aiosqlite", "")

_engine_kwargs = {} if "sqlite" in _SYNC_DB_URL else {
    "pool_size": 5,
    "max_overflow": 10,
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

sync_engine = create_engine(_SYNC_DB_URL, **_engine_kwargs)
SyncSession = sessionmaker(sync_engine, expire_on_commit=False)


# ---------------------------------------------------------------------------
# Task: process_heartbeat
# ---------------------------------------------------------------------------
@celery_app.task(
    name="services.host_service.tasks.process_heartbeat",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def process_heartbeat(
    self,
    host_id: str,
    status: str,
    temperature_c: float | None = None,
    power_draw_w: float | None = None,
    gpu_utilization_pct: float | None = None,
    ram_used_gb: float | None = None,
) -> dict:
    """
    Async Celery task to process and store a host heartbeat.

    Decoupled from the HTTP path so the heartbeat endpoint can return
    immediately, and the DB write happens in the background worker.
    This allows high-frequency heartbeats without blocking the API.
    """
    try:
        with SyncSession() as session:
            # Upsert: just insert new heartbeat row (time-series append pattern)
            hb = HostHeartbeat(
                host_id=uuid.UUID(host_id),
                status=HeartbeatStatus(status),
                temperature_c=temperature_c,
                power_draw_w=power_draw_w,
                gpu_utilization_pct=gpu_utilization_pct,
                ram_used_gb=ram_used_gb,
            )
            session.add(hb)
            session.commit()
            logger.info("heartbeat_processed", host_id=host_id, status=status)
            return {"host_id": host_id, "status": status, "processed": True}
    except Exception as exc:
        logger.error("heartbeat_processing_failed", host_id=host_id, error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task: trigger_rebenchmark
# ---------------------------------------------------------------------------
@celery_app.task(
    name="services.host_service.tasks.trigger_rebenchmark",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def trigger_rebenchmark(self, host_id: str) -> dict:
    """
    Signal a host agent to run its benchmark suite again.

    In Phase 2, this publishes a rebenchmark command to a Redis pub/sub channel
    that the Host Agent subscribes to. The agent runs benchmarks and submits
    results to POST /hosts/{host_id}/benchmarks.

    Phase 5 (Security Hardening) will sign these commands with HMAC to prevent
    a malicious actor from forcing a benchmark on a host they don't own.
    """
    import redis as sync_redis
    try:
        r = sync_redis.from_url(settings.redis_url)
        channel = f"kynetic:host:{host_id}:commands"
        r.publish(channel, '{"command": "rebenchmark"}')
        logger.info("rebenchmark_signal_sent", host_id=host_id, channel=channel)
        return {"host_id": host_id, "command_sent": True}
    except Exception as exc:
        logger.error("rebenchmark_signal_failed", host_id=host_id, error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task: rebenchmark_sweep (periodic — Celery Beat)
# ---------------------------------------------------------------------------
@celery_app.task(
    name="services.host_service.tasks.rebenchmark_sweep",
    bind=True,
)
def rebenchmark_sweep(self) -> dict:
    """
    Periodic task (every hour): find all verified hosts whose last benchmark
    is older than rebenchmark_interval_hours, and enqueue trigger_rebenchmark.

    This implements the continuous host verification requirement from
    Security Pillar 3 (MVP tier) — catching degraded or tampered hardware
    post-onboarding.
    """
    from libs.db_models.host_models import HostBenchmark
    from sqlalchemy import func

    interval_hours = settings.rebenchmark_interval_hours
    cutoff = datetime.now(UTC) - timedelta(hours=interval_hours)

    enqueued = 0
    try:
        with SyncSession() as session:
            # Find hosts with last benchmark older than cutoff, or no benchmark at all
            last_run_sq = (
                select(
                    HostBenchmark.host_id,
                    func.max(HostBenchmark.run_at).label("last_run")
                )
                .group_by(HostBenchmark.host_id)
                .subquery()
            )
            stale_hosts = session.execute(
                select(Host.id)
                .join(last_run_sq, Host.id == last_run_sq.c.host_id, isouter=True)
                .where(
                    Host.status.in_([HostStatus.VERIFIED, HostStatus.LISTED]),
                    (last_run_sq.c.last_run == None) | (last_run_sq.c.last_run < cutoff),  # noqa: E711
                )
            ).scalars().all()

            for host_id in stale_hosts:
                trigger_rebenchmark.delay(str(host_id))
                enqueued += 1

        logger.info("rebenchmark_sweep_complete", enqueued=enqueued, cutoff=cutoff.isoformat())
        return {"enqueued": enqueued}
    except Exception as exc:
        logger.error("rebenchmark_sweep_failed", error=str(exc))
        raise self.retry(exc=exc)


# ---------------------------------------------------------------------------
# Task: mark_offline_sweep (periodic — Celery Beat)
# ---------------------------------------------------------------------------
@celery_app.task(
    name="services.host_service.tasks.mark_offline_sweep",
    bind=True,
)
def mark_offline_sweep(self) -> dict:
    """
    Periodic task (every 10 minutes): mark hosts offline if no heartbeat has
    been received within heartbeat_timeout_seconds.

    Uses a DB query against the latest heartbeat per host rather than
    an in-memory set — more reliable across Celery worker restarts.
    """
    from sqlalchemy import func

    timeout = settings.heartbeat_timeout_seconds
    cutoff = datetime.now(UTC) - timedelta(seconds=timeout)
    marked_offline = 0

    try:
        with SyncSession() as session:
            # Subquery: last heartbeat per host
            last_hb_sq = (
                select(
                    HostHeartbeat.host_id,
                    func.max(HostHeartbeat.recorded_at).label("last_seen")
                )
                .group_by(HostHeartbeat.host_id)
                .subquery()
            )
            stale_host_ids = session.execute(
                select(Host.id)
                .join(last_hb_sq, Host.id == last_hb_sq.c.host_id, isouter=True)
                .where(
                    Host.status.notin_([HostStatus.SUSPENDED, HostStatus.FLAGGED]),
                    (last_hb_sq.c.last_seen == None) | (last_hb_sq.c.last_seen < cutoff),  # noqa: E711
                )
            ).scalars().all()

            if stale_host_ids:
                session.execute(
                    update(Host)
                    .where(Host.id.in_(stale_host_ids))
                    .values(status=HostStatus.PENDING_VERIFICATION, updated_at=datetime.now(UTC))
                )
                session.commit()
                marked_offline = len(stale_host_ids)

        logger.info("offline_sweep_complete", marked_offline=marked_offline)
        return {"marked_offline": marked_offline}
    except Exception as exc:
        logger.error("offline_sweep_failed", error=str(exc))
        raise self.retry(exc=exc)
