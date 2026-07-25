"""
Phase 28 — Status Sync (provisioning_service/status_sync.py)

Called by the provisioning Celery task immediately after an instance transitions
state. Publishes lifecycle events to the internal event bus so the billing
service can start/stop metering in real-time.

This module owns the "publish" side of Phase 28's billing event integration.
The "subscribe" side lives in wallet_billing_service/event_handlers.py.

Design:
  - Receives structured data from the Celery task (already verified DB rows).
  - Builds the canonical event payload (typed dict with all fields billing needs).
  - Publishes non-blocking; failures are logged and surfaced as warnings — the
    reconciliation sweep (tasks.py sweep_billing_meters) provides the safety net.
  - `update_instance_status` wrapper kept separate so this module is purely about
    events, not state machine logic (which lives in repository.py).

Event payloads published here:

  INSTANCE_RUNNING:
    instance_id, developer_id, listing_id, price_per_second_usd,
    price_per_second_inr, preferred_currency, started_at

  INSTANCE_TERMINATED:
    instance_id, developer_id, listing_id, stopped_at, reason,
    billed_seconds (actual runtime in seconds, for finalize_billing)

  INSTANCE_FAILED:
    instance_id, developer_id, failed_at, reason
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import structlog

from libs.events.bus import (
    INSTANCE_FAILED,
    INSTANCE_RUNNING,
    INSTANCE_TERMINATED,
    publish_event,
)

log = structlog.get_logger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def on_instance_running(
    *,
    instance_id: uuid.UUID | str,
    developer_id: uuid.UUID | str,
    listing_id: uuid.UUID | str,
    price_per_second_usd: str,
    price_per_second_inr: str,
    preferred_currency: str,        # "usd" | "inr"
    started_at: str | None = None,  # ISO-8601; defaults to now()
) -> None:
    """
    Publish INSTANCE_RUNNING event.

    Called from `_provision_instance_async` (tasks.py) immediately after
    `instance_repo.transition_state(iid, InstanceStatus.running)` succeeds.

    Args:
        instance_id:          The running instance.
        developer_id:         Owner — billing will debit this wallet.
        listing_id:           Source listing — used for rate look-up if needed.
        price_per_second_usd: String Decimal, e.g. "0.0002777778".
        price_per_second_inr: String Decimal, e.g. "0.023333".
        preferred_currency:   "usd" or "inr" — which balance to debit.
        started_at:           Override start time (for replay/testing).
    """
    payload = {
        "instance_id":          str(instance_id),
        "developer_id":         str(developer_id),
        "listing_id":           str(listing_id),
        "price_per_second_usd": price_per_second_usd,
        "price_per_second_inr": price_per_second_inr,
        "preferred_currency":   preferred_currency,
        "started_at":           started_at or _now_iso(),
    }
    log.info("status_sync.instance_running", **payload)
    await publish_event(INSTANCE_RUNNING, payload)


async def on_instance_terminated(
    *,
    instance_id: uuid.UUID | str,
    developer_id: uuid.UUID | str,
    listing_id: uuid.UUID | str,
    stopped_at: str | None = None,
    reason: str = "user_requested",
    billed_seconds: int = 0,
) -> None:
    """
    Publish INSTANCE_TERMINATED event.

    Called from `_terminate_instance_async` (tasks.py) immediately after
    the instance transitions to `terminated`.

    `billed_seconds` is the actual runtime (not the hold hours). The billing
    service uses this to compute the final debit and release the unused hold.
    """
    payload = {
        "instance_id":    str(instance_id),
        "developer_id":   str(developer_id),
        "listing_id":     str(listing_id),
        "stopped_at":     stopped_at or _now_iso(),
        "reason":         reason,
        "billed_seconds": billed_seconds,
    }
    log.info("status_sync.instance_terminated", **payload)
    await publish_event(INSTANCE_TERMINATED, payload)


async def on_instance_failed(
    *,
    instance_id: uuid.UUID | str,
    developer_id: uuid.UUID | str,
    reason: str,
    failed_at: str | None = None,
) -> None:
    """
    Publish INSTANCE_FAILED event.

    Called when provisioning fails (image scan blocked, agent unreachable,
    etc.) so billing can immediately release the wallet hold.
    """
    payload = {
        "instance_id": str(instance_id),
        "developer_id": str(developer_id),
        "reason":       reason,
        "failed_at":    failed_at or _now_iso(),
    }
    log.info("status_sync.instance_failed", **payload)
    await publish_event(INSTANCE_FAILED, payload)
