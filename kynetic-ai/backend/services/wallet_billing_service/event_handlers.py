"""
Phase 28 — Billing Event Handlers (wallet_billing_service/event_handlers.py)

Subscribes to the internal Redis pub/sub event bus and bridges lifecycle
events from the Provisioning Service into real-time billing state changes.

Responsibilities:
  INSTANCE_RUNNING   → call start_metering() → schedules debit_running_instance
  INSTANCE_TERMINATED→ call stop_metering() + finalize_billing()
  INSTANCE_FAILED    → call release_hold_for_failed_instance()

Each handler runs in its own asyncio task (started in main.py on startup).
Failures in a handler are logged and the loop continues — a single bad event
should never take down the whole subscriber.

Flow on INSTANCE_RUNNING:
  1. Look up Instance + Wallet from DB (for rate + preferred_currency)
  2. Insert BillingMeterJob row (tracks the active debit task)
  3. Dispatch debit_running_instance Celery periodic task

Flow on INSTANCE_TERMINATED:
  1. Stop the metering Celery task (revoke by task_id from BillingMeterJob)
  2. Compute actual billed amount: billed_seconds * price_per_second
  3. Compute unused hold: hold_amount - actual_billed
  4. Refund unused hold as a 'refund' WalletTransaction
  5. Mark BillingMeterJob stopped_at
  6. Update instance.hold_released = True (via provisioning service internal API)

Flow on INSTANCE_FAILED:
  1. If a hold was placed, issue a full refund WalletTransaction
  2. Mark instance.hold_released = True

Thread safety:
  All DB access uses a fresh sync SQLAlchemy session per event (Celery-compatible).
  All event handlers are `async def` and run in the FastAPI/asyncio event loop.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

import structlog
from sqlalchemy import create_engine, select, update as sa_update
from sqlalchemy.orm import Session

from libs.events.bus import (
    ALL_INSTANCE_CHANNELS,
    INSTANCE_FAILED,
    INSTANCE_RUNNING,
    INSTANCE_TERMINATED,
    subscribe_many,
)
from services.wallet_billing_service.config import get_settings

log = structlog.get_logger(__name__)

AMOUNT_PRECISION = Decimal("0.000001")


# ── DB session helper (sync, for Celery + event handler compatibility) ────────

def _sync_session() -> Session:
    settings = get_settings()
    sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    return Session(engine)


# ── Metering start ─────────────────────────────────────────────────────────────

def _handle_instance_running(event: dict) -> None:
    """
    Triggered by INSTANCE_RUNNING event.
    Records a BillingMeterJob and dispatches the periodic debit task.
    Safe to call multiple times (idempotent via unique constraint on instance_id).
    """
    instance_id = event.get("instance_id")
    developer_id = event.get("developer_id")

    if not instance_id:
        log.warning("billing.running_event_missing_instance_id", event=event)
        return

    log.info("billing.start_metering", instance_id=instance_id, developer_id=developer_id)

    try:
        from services.wallet_billing_service.metering import (
            BillingMeterJobRepo,
            debit_running_instance,
        )

        with _sync_session() as session:
            with session.begin():
                repo = BillingMeterJobRepo(session)
                # Idempotency: skip if already metering
                existing = repo.get_by_instance(uuid.UUID(instance_id))
                if existing:
                    log.debug(
                        "billing.already_metering_skip",
                        instance_id=instance_id,
                    )
                    return

                # Dispatch the periodic debit task
                result = debit_running_instance.apply_async(
                    args=[instance_id],
                    countdown=10,  # first debit after 10 seconds
                )

                repo.create(
                    instance_id=uuid.UUID(instance_id),
                    celery_task_id=result.id,
                )

        log.info(
            "billing.metering_started",
            instance_id=instance_id,
            celery_task_id=result.id,
        )

    except Exception as exc:
        log.error("billing.start_metering_failed", instance_id=instance_id, error=str(exc))


# ── Billing finalization on termination ───────────────────────────────────────

def _handle_instance_terminated(event: dict) -> None:
    """
    Triggered by INSTANCE_TERMINATED event.
    Stops metering, finalizes billing, refunds unused hold.
    Idempotent: skips if hold_released is already True.
    """
    instance_id = event.get("instance_id")
    developer_id = event.get("developer_id")
    billed_seconds = int(event.get("billed_seconds", 0))

    if not instance_id:
        log.warning("billing.terminated_event_missing_instance_id", event=event)
        return

    log.info(
        "billing.stop_metering",
        instance_id=instance_id,
        billed_seconds=billed_seconds,
    )

    try:
        from services.wallet_billing_service.metering import BillingMeterJobRepo
        from libs.db_models.provisioning_models import Instance
        from libs.db_models.marketplace_models import (
            Currency,
            TransactionType,
            Wallet,
            WalletTransaction,
        )

        with _sync_session() as session:
            with session.begin():
                # ── 1. Stop the metering task ─────────────────────────────────
                repo = BillingMeterJobRepo(session)
                job = repo.get_by_instance(uuid.UUID(instance_id))
                if job:
                    try:
                        from celery.app.control import Control
                        from services.wallet_billing_service.celery_app import celery_app
                        Control(celery_app).revoke(job.celery_task_id, terminate=True)
                    except Exception as revoke_exc:
                        log.warning(
                            "billing.revoke_task_failed",
                            instance_id=instance_id,
                            task_id=job.celery_task_id,
                            error=str(revoke_exc),
                        )
                    repo.mark_stopped(job)

                # ── 2. Load instance row ──────────────────────────────────────
                instance = session.execute(
                    select(Instance).where(Instance.id == uuid.UUID(instance_id))
                ).scalar_one_or_none()

                if not instance:
                    log.error("billing.instance_not_found_for_finalize", instance_id=instance_id)
                    return

                if instance.hold_released:
                    log.debug("billing.hold_already_released", instance_id=instance_id)
                    return

                # ── 3. Compute actual billed cost ─────────────────────────────
                settings = get_settings()
                rate = Decimal(settings.usd_to_inr_rate)

                price_usd = Decimal(str(instance.price_per_second_usd))
                price_inr  = Decimal(str(getattr(instance, "price_per_second_inr", 0) or 0))
                actual_usd = (price_usd * Decimal(billed_seconds)).quantize(
                    AMOUNT_PRECISION, rounding=ROUND_HALF_UP
                )
                actual_inr = (price_inr * Decimal(billed_seconds)).quantize(
                    AMOUNT_PRECISION, rounding=ROUND_HALF_UP
                )

                hold_usd = Decimal(str(instance.hold_amount or 0)).quantize(AMOUNT_PRECISION)

                # ── 4. Compute refund = hold - actual_billed ──────────────────
                refund_usd = max(hold_usd - actual_usd, Decimal("0"))
                refund_inr = (refund_usd * rate).quantize(AMOUNT_PRECISION, rounding=ROUND_HALF_UP)

                # ── 5. Write refund WalletTransaction (if there's anything to refund) ──
                if refund_usd > Decimal("0"):
                    wallet = session.execute(
                        select(Wallet).where(Wallet.user_id == instance.developer_id)
                    ).scalar_one_or_none()

                    if wallet:
                        wallet.balance_usd = (wallet.balance_usd + refund_usd).quantize(AMOUNT_PRECISION)
                        wallet.balance_inr = (wallet.balance_inr + refund_inr).quantize(AMOUNT_PRECISION)

                        txn = WalletTransaction(
                            wallet_id=wallet.id,
                            transaction_type=TransactionType.refund,
                            amount=refund_usd,
                            currency=Currency.usd,
                            listing_id=instance.listing_id,
                            description=(
                                f"Hold refund: {billed_seconds}s billed of {int(hold_usd / price_usd) if price_usd else 0}s held "
                                f"on instance {instance_id[:8]}"
                            ),
                            balance_after_usd=wallet.balance_usd,
                            balance_after_inr=wallet.balance_inr,
                        )
                        session.add(txn)

                        log.info(
                            "billing.hold_refunded",
                            instance_id=instance_id,
                            refund_usd=float(refund_usd),
                            actual_billed_usd=float(actual_usd),
                        )

                # ── 6. Mark hold released ─────────────────────────────────────
                session.execute(
                    sa_update(Instance)
                    .where(Instance.id == uuid.UUID(instance_id))
                    .values(hold_released=True)
                )

        log.info("billing.finalized", instance_id=instance_id, billed_seconds=billed_seconds)

    except Exception as exc:
        log.error(
            "billing.finalize_failed",
            instance_id=instance_id,
            error=str(exc),
        )


# ── Hold release on failed instance ──────────────────────────────────────────

def _handle_instance_failed(event: dict) -> None:
    """
    Triggered by INSTANCE_FAILED event.
    Releases the full wallet hold since the instance never ran.
    """
    instance_id = event.get("instance_id")
    developer_id = event.get("developer_id")

    if not instance_id:
        return

    log.info("billing.release_hold_on_failure", instance_id=instance_id)

    try:
        from libs.db_models.provisioning_models import Instance
        from libs.db_models.marketplace_models import (
            Currency,
            TransactionType,
            Wallet,
            WalletTransaction,
        )

        with _sync_session() as session:
            with session.begin():
                instance = session.execute(
                    select(Instance).where(Instance.id == uuid.UUID(instance_id))
                ).scalar_one_or_none()

                if not instance or instance.hold_released:
                    return

                hold_usd = Decimal(str(instance.hold_amount or 0)).quantize(AMOUNT_PRECISION)

                if hold_usd > Decimal("0"):
                    settings = get_settings()
                    rate = Decimal(settings.usd_to_inr_rate)
                    hold_inr = (hold_usd * rate).quantize(AMOUNT_PRECISION, rounding=ROUND_HALF_UP)

                    wallet = session.execute(
                        select(Wallet).where(Wallet.user_id == instance.developer_id)
                    ).scalar_one_or_none()

                    if wallet:
                        wallet.balance_usd = (wallet.balance_usd + hold_usd).quantize(AMOUNT_PRECISION)
                        wallet.balance_inr = (wallet.balance_inr + hold_inr).quantize(AMOUNT_PRECISION)

                        txn = WalletTransaction(
                            wallet_id=wallet.id,
                            transaction_type=TransactionType.refund,
                            amount=hold_usd,
                            currency=Currency.usd,
                            listing_id=instance.listing_id,
                            description=f"Full hold refund — instance {instance_id[:8]} failed before start",
                            balance_after_usd=wallet.balance_usd,
                            balance_after_inr=wallet.balance_inr,
                        )
                        session.add(txn)
                        log.info(
                            "billing.full_hold_refunded_on_failure",
                            instance_id=instance_id,
                            refund_usd=float(hold_usd),
                        )

                session.execute(
                    sa_update(Instance)
                    .where(Instance.id == uuid.UUID(instance_id))
                    .values(hold_released=True)
                )

    except Exception as exc:
        log.error("billing.release_hold_failed", instance_id=instance_id, error=str(exc))


# ── Event dispatch router ─────────────────────────────────────────────────────

_HANDLERS = {
    INSTANCE_RUNNING:    _handle_instance_running,
    INSTANCE_TERMINATED: _handle_instance_terminated,
    INSTANCE_FAILED:     _handle_instance_failed,
}


async def _run_billing_event_loop() -> None:
    """
    Single async loop that subscribes to ALL instance lifecycle channels.
    Routes each message to the correct handler.
    Handlers are called synchronously within the loop (they use sync DB sessions)
    to avoid concurrent DB conflicts on the same instance.
    """
    log.info("billing_event_loop.starting")
    try:
        async for channel, event in subscribe_many(*ALL_INSTANCE_CHANNELS):
            handler = _HANDLERS.get(channel)
            if handler is None:
                log.warning("billing_event_loop.unknown_channel", channel=channel)
                continue
            try:
                handler(event)
            except Exception as exc:
                log.error(
                    "billing_event_loop.handler_error",
                    channel=channel,
                    instance_id=event.get("instance_id"),
                    error=str(exc),
                )
    except asyncio.CancelledError:
        log.info("billing_event_loop.cancelled")
    except Exception as exc:
        log.error("billing_event_loop.crashed", error=str(exc))


def start_billing_event_listeners() -> asyncio.Task:
    """
    Launch the billing event loop as a background asyncio task.
    Call this from the wallet_billing_service FastAPI startup handler.

    Returns the Task so it can be cancelled on shutdown.
    """
    task = asyncio.create_task(
        _run_billing_event_loop(),
        name="billing_event_loop",
    )
    log.info("billing_event_listeners.started")
    return task
