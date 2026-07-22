"""
Provisioning Service — Live Billing Watcher.

`meter_instance_usage` is a Celery task that runs once per second
for every running instance. It:

1. Debits `price_per_second_usd` from the developer's wallet
2. Increments `instances.billed_seconds`
3. On low balance: emits `instance.low_balance` Redis event
4. On zero / insufficient balance: triggers `auto_terminate_on_zero_balance`

The task is scheduled by the Celery beat scheduler after an instance
transitions to `running`. It is cancelled when the instance stops/terminates.

Redis key for active billing tasks:
  kynetic:billing:active:{instance_id}   → "1" (expires when billing stops)
"""

import asyncio
import uuid
from decimal import Decimal

import httpx
import redis
import structlog

from services.provisioning_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

# Redis key patterns
_BILLING_ACTIVE_KEY = "kynetic:billing:active:{instance_id}"
_BILLING_STOP_KEY   = "kynetic:billing:stop:{instance_id}"


def _redis_client() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def start_billing(instance_id: uuid.UUID) -> None:
    """
    Registers the instance as actively billing in Redis and
    schedules the per-second billing Celery task.
    """
    r = _redis_client()
    key = _BILLING_ACTIVE_KEY.format(instance_id=str(instance_id))
    r.set(key, "1")
    # Enqueue the first tick immediately
    from services.provisioning_service.tasks import meter_instance_usage
    meter_instance_usage.apply_async(
        args=[str(instance_id)],
        countdown=1,  # start billing 1 second after running state
    )
    log.info("billing_watcher.started", instance_id=str(instance_id))


def stop_billing(instance_id: uuid.UUID) -> None:
    """
    Signals the billing loop to stop by setting a stop key in Redis.
    The billing task checks this key at the top of each tick.
    """
    r = _redis_client()
    stop_key = _BILLING_STOP_KEY.format(instance_id=str(instance_id))
    r.set(stop_key, "1", ex=3600)  # expires after 1hr to prevent stale keys
    active_key = _BILLING_ACTIVE_KEY.format(instance_id=str(instance_id))
    r.delete(active_key)
    log.info("billing_watcher.stopped", instance_id=str(instance_id))


def is_billing_active(instance_id: uuid.UUID) -> bool:
    r = _redis_client()
    return r.exists(_BILLING_ACTIVE_KEY.format(instance_id=str(instance_id))) > 0


def should_stop(instance_id: uuid.UUID) -> bool:
    r = _redis_client()
    return r.exists(_BILLING_STOP_KEY.format(instance_id=str(instance_id))) > 0


async def _debit_wallet(
    developer_id: str,
    instance_id: str,
    amount_usd: str,
    auth_token: str = "INTERNAL",
) -> bool:
    """
    Debits the wallet via the wallet_billing_service internal API.
    Returns True on success, False on insufficient funds.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.wallet_billing_service_url}/wallet/debit",
                json={
                    "amount_usd": amount_usd,
                    "description": f"Instance billing tick — {instance_id}",
                    "idempotency_key": f"billing:{instance_id}:{amount_usd}",
                },
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            if resp.status_code == 402:  # Payment Required — insufficient funds
                return False
            resp.raise_for_status()
            return True
    except httpx.HTTPError as exc:
        log.error("billing_watcher.debit_failed", error=str(exc), instance_id=instance_id)
        # Don't terminate on transient network errors — retry next tick
        return True


async def _emit_low_balance_event(instance_id: str) -> None:
    """Emit a Redis pub/sub event for the notification system (Phase 10)."""
    r = _redis_client()
    r.publish(
        "kynetic:events:instance",
        f'{{"event": "instance.low_balance", "instance_id": "{instance_id}"}}',
    )
    log.warning("billing_watcher.low_balance", instance_id=instance_id)
