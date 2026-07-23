"""
Provisioning Service — Live Billing Watcher.
# ponytail: direct Redis billing state manager (saved 65 lines)
"""

import uuid
import httpx
import redis
import structlog

from services.provisioning_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

_ACTIVE_KEY = "kynetic:billing:active:{instance_id}"
_STOP_KEY = "kynetic:billing:stop:{instance_id}"


def _redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def start_billing(instance_id: uuid.UUID) -> None:
    r = _redis()
    r.set(_ACTIVE_KEY.format(instance_id=str(instance_id)), "1")
    from services.provisioning_service.tasks import meter_instance_usage
    meter_instance_usage.apply_async(args=[str(instance_id)], countdown=1)


def stop_billing(instance_id: uuid.UUID) -> None:
    r = _redis()
    r.set(_STOP_KEY.format(instance_id=str(instance_id)), "1", ex=3600)
    r.delete(_ACTIVE_KEY.format(instance_id=str(instance_id)))


def is_billing_active(instance_id: uuid.UUID) -> bool:
    return bool(_redis().exists(_ACTIVE_KEY.format(instance_id=str(instance_id))))


def should_stop(instance_id: uuid.UUID) -> bool:
    return bool(_redis().exists(_STOP_KEY.format(instance_id=str(instance_id))))


async def _debit_wallet(developer_id: str, instance_id: str, amount_usd: str, auth_token: str = "INTERNAL") -> bool:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{settings.wallet_billing_service_url}/wallet/debit",
                json={"amount_usd": amount_usd, "description": f"Instance tick {instance_id}"},
                headers={"Authorization": f"Bearer {auth_token}"},
            )
            return resp.status_code != 402
    except Exception:
        return True


async def _emit_low_balance_event(instance_id: str) -> None:
    _redis().publish("kynetic:events:instance", f'{{"event": "instance.low_balance", "instance_id": "{instance_id}"}}')
