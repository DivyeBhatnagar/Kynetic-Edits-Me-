"""
Phase 28 — Per-Second Billing Metering (wallet_billing_service/metering.py)

Celery task: debit_running_instance
  - Called every 10 seconds for each running instance.
  - Self-rescheduling until the instance stops.
  - Atomic DB debit: balance decrement + WalletTransaction append in one transaction.
  - Auto-terminates the instance if balance reaches zero.

DB model: BillingMeterJob
  - One row per running instance.
  - Tracks the active Celery task_id so it can be revoked on termination.
  - Records billed_seconds_total (mirror of instances.billed_seconds, for the billing service).

Design decisions:
  - 10-second tick interval balances precision vs. DB write throughput.
    At $1/hr the tick debit is $0.0000277 USD — fine-grained enough for fairness.
  - Self-rescheduling tasks (not Beat cron) because each instance has an
    independent lifecycle; Beat would require maintaining a dynamic schedule.
  - The metering task checks `should_stop()` from billing_watcher via Redis
    as a fast-path kill signal without a DB read.
  - All Decimal arithmetic uses ROUND_HALF_UP to prevent systematic drift.

Security note:
  - Amount is read from DB (not from the event payload) to prevent a tampered
    event from changing the debit rate. The rate in the event payload is for
    logging only.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import structlog
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from libs.db_models.database import Base
from services.wallet_billing_service.celery_app import celery_app
from services.wallet_billing_service.config import get_settings

log = structlog.get_logger(__name__)

AMOUNT_PRECISION = Decimal("0.000001")
TICK_SECONDS = 10  # debit interval


# ── ORM Model: billing_meter_jobs ─────────────────────────────────────────────

class BillingMeterJob(Base):
    """
    Phase 28 — tracks one active per-second billing loop per instance.

    Created when INSTANCE_RUNNING fires.
    Updated (stopped_at set) when INSTANCE_TERMINATED fires.
    The celery_task_id is used to revoke the debit task on termination.
    """
    __tablename__ = "billing_meter_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one metering job per instance
        index=True,
    )
    celery_task_id: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="Task ID of the running debit_running_instance Celery chain",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_debited_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    billed_seconds_total: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    __table_args__ = (
        Index("ix_billing_meter_jobs_instance", "instance_id"),
        Index("ix_billing_meter_jobs_active", "instance_id", "stopped_at"),
    )


# ── Repository ────────────────────────────────────────────────────────────────

class BillingMeterJobRepo:
    """Sync repository for BillingMeterJob — compatible with Celery tasks."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, instance_id: uuid.UUID, celery_task_id: str) -> BillingMeterJob:
        job = BillingMeterJob(
            instance_id=instance_id,
            celery_task_id=celery_task_id,
        )
        self._session.add(job)
        self._session.flush()
        return job

    def get_by_instance(self, instance_id: uuid.UUID) -> BillingMeterJob | None:
        return self._session.execute(
            select(BillingMeterJob)
            .where(BillingMeterJob.instance_id == instance_id)
            .where(BillingMeterJob.stopped_at.is_(None))
        ).scalar_one_or_none()

    def mark_stopped(self, job: BillingMeterJob) -> None:
        job.stopped_at = datetime.now(timezone.utc)
        self._session.flush()

    def increment_billed(self, job: BillingMeterJob, seconds: int = TICK_SECONDS) -> None:
        job.billed_seconds_total += seconds
        job.last_debited_at = datetime.now(timezone.utc)
        self._session.flush()


# ── Sync DB session ───────────────────────────────────────────────────────────

def _get_sync_session() -> Session:
    settings = get_settings()
    sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    return Session(engine)


# ── Celery task: periodic debit ───────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="services.wallet_billing_service.tasks.debit_running_instance",
    max_retries=5,
    default_retry_delay=5,
    acks_late=True,   # Only ack after successful completion (no double-billing)
)
def debit_running_instance(self, instance_id: str) -> dict:
    """
    Per-tick billing debit for a running instance.

    Debits TICK_SECONDS of compute cost from the developer's wallet, then
    reschedules itself for the next tick. Stops automatically if:
      - Redis stop signal is set (billing_watcher.should_stop)
      - Instance is no longer in 'running' state
      - Wallet balance reaches zero (triggers auto-terminate)

    All amounts use Decimal arithmetic — no float in the billing path.
    """
    from libs.db_models.provisioning_models import Instance, InstanceStatus
    from libs.db_models.marketplace_models import (
        Currency,
        TransactionType,
        Wallet,
        WalletTransaction,
    )
    # Fast-path Redis stop signal check (avoids DB round-trip on already-stopped instances)
    try:
        from services.provisioning_service.billing_watcher import should_stop
        if should_stop(uuid.UUID(instance_id)):
            log.info("debit_running_instance.redis_stop_signal", instance_id=instance_id)
            return {"stopped": True, "reason": "redis_stop_signal"}
    except Exception:
        pass  # billing_watcher may not be reachable from billing service; fall through to DB check

    settings = get_settings()
    rate = Decimal(settings.usd_to_inr_rate)
    iid = uuid.UUID(instance_id)

    try:
        with _get_sync_session() as session:
            with session.begin():
                # ── Load instance (authoritative rate source, NOT event payload) ──
                instance = session.execute(
                    select(Instance).where(Instance.id == iid)
                ).scalar_one_or_none()

                if not instance:
                    log.warning("debit_running_instance.instance_not_found", instance_id=instance_id)
                    return {"stopped": True, "reason": "not_found"}

                if instance.status != InstanceStatus.running:
                    log.info(
                        "debit_running_instance.not_running",
                        instance_id=instance_id,
                        status=instance.status.value,
                    )
                    return {"stopped": True, "reason": f"status_{instance.status.value}"}

                # ── Compute debit amount ───────────────────────────────────────
                price_per_second_usd = Decimal(str(instance.price_per_second_usd))
                debit_usd = (price_per_second_usd * Decimal(TICK_SECONDS)).quantize(
                    AMOUNT_PRECISION, rounding=ROUND_HALF_UP
                )
                # Minimum debit floor to avoid zero-amount transactions on very cheap listings
                if debit_usd < Decimal("0.000001"):
                    debit_usd = Decimal("0.000001")

                debit_inr = (debit_usd * rate).quantize(AMOUNT_PRECISION, rounding=ROUND_HALF_UP)

                # ── Load wallet ────────────────────────────────────────────────
                wallet = session.execute(
                    select(Wallet).where(Wallet.user_id == instance.developer_id)
                ).scalar_one_or_none()

                if not wallet:
                    log.error(
                        "debit_running_instance.wallet_not_found",
                        instance_id=instance_id,
                        developer_id=str(instance.developer_id),
                    )
                    # Terminate to protect host — we can't bill them
                    _trigger_auto_terminate(instance_id, reason="wallet_disappeared")
                    return {"stopped": True, "reason": "wallet_not_found"}

                # ── Check balance ──────────────────────────────────────────────
                preferred = str(getattr(wallet, "preferred_currency", "usd") or "usd")
                if preferred == "inr":
                    balance_check = wallet.balance_inr
                    debit_check = debit_inr
                else:
                    balance_check = wallet.balance_usd
                    debit_check = debit_usd

                if balance_check <= Decimal("0"):
                    log.warning(
                        "debit_running_instance.zero_balance_auto_terminate",
                        instance_id=instance_id,
                        balance=float(balance_check),
                    )
                    _trigger_auto_terminate(instance_id, reason="zero_balance_auto_termination")
                    return {"stopped": True, "reason": "zero_balance"}

                # ── Atomic debit ───────────────────────────────────────────────
                new_usd = (wallet.balance_usd - debit_usd).quantize(AMOUNT_PRECISION)
                new_inr = (wallet.balance_inr - debit_inr).quantize(AMOUNT_PRECISION)
                # Guard against underflow
                new_usd = max(new_usd, Decimal("0"))
                new_inr = max(new_inr, Decimal("0"))

                wallet.balance_usd = new_usd
                wallet.balance_inr = new_inr

                txn = WalletTransaction(
                    wallet_id=wallet.id,
                    transaction_type=TransactionType.debit,
                    amount=debit_usd,
                    currency=Currency.usd,
                    listing_id=instance.listing_id,
                    description=f"Compute usage: {TICK_SECONDS}s @ ${price_per_second_usd}/s — instance {instance_id[:8]}",
                    balance_after_usd=new_usd,
                    balance_after_inr=new_inr,
                )
                session.add(txn)

                # ── Increment billed_seconds on instance row ───────────────────
                instance.billed_seconds = (instance.billed_seconds or 0) + TICK_SECONDS

                # ── Update metering job row ────────────────────────────────────
                repo = BillingMeterJobRepo(session)
                job = repo.get_by_instance(iid)
                if job:
                    repo.increment_billed(job, TICK_SECONDS)

        log.debug(
            "debit_running_instance.tick",
            instance_id=instance_id,
            debit_usd=float(debit_usd),
            new_balance_usd=float(new_usd),
        )

        # ── Reschedule for next tick ───────────────────────────────────────────
        debit_running_instance.apply_async(
            args=[instance_id],
            countdown=TICK_SECONDS,
        )
        return {"debited_usd": float(debit_usd), "tick_seconds": TICK_SECONDS}

    except Exception as exc:
        log.error(
            "debit_running_instance.error",
            instance_id=instance_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)


def _trigger_auto_terminate(instance_id: str, reason: str) -> None:
    """Fire a terminate_instance Celery task (non-blocking)."""
    try:
        from services.provisioning_service.celery_app import celery_app as prov_app
        prov_app.send_task("terminate_instance", args=[instance_id, reason])
    except Exception as exc:
        log.error(
            "debit_running_instance.trigger_terminate_failed",
            instance_id=instance_id,
            error=str(exc),
        )


# ── Reconciliation sweep (Celery Beat, every 60s) ─────────────────────────────

@celery_app.task(name="services.wallet_billing_service.tasks.sweep_billing_meters")
def sweep_billing_meters() -> dict:
    """
    Periodic sweep task (run by Celery Beat every 60s).

    Finds instances that are in 'running' state but have no active
    BillingMeterJob (e.g., after a worker restart or missed event).
    Restarts metering for those instances.

    This is the safety net for missed INSTANCE_RUNNING events.
    """
    from libs.db_models.provisioning_models import Instance, InstanceStatus

    restarted = []
    with _get_sync_session() as session:
        with session.begin():
            # All instances currently running
            running_instances = session.execute(
                select(Instance).where(Instance.status == InstanceStatus.running)
            ).scalars().all()

            repo = BillingMeterJobRepo(session)
            for instance in running_instances:
                job = repo.get_by_instance(instance.id)
                if job is None:
                    # No active metering job — restart it
                    log.warning(
                        "sweep_billing_meters.no_active_job_restarting",
                        instance_id=str(instance.id),
                    )
                    result = debit_running_instance.apply_async(
                        args=[str(instance.id)],
                        countdown=1,
                    )
                    repo.create(
                        instance_id=instance.id,
                        celery_task_id=result.id,
                    )
                    restarted.append(str(instance.id))

    log.info("sweep_billing_meters.complete", restarted_count=len(restarted), restarted=restarted)
    return {"restarted": restarted}
