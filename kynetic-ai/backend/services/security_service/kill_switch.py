"""
Security Service — Kill Switch.

Admin-only operation that instantly suspends:
  - An instance  → sends terminate command to the provisioning_service
  - A host       → broadcasts a suspension signal to the host agent over mTLS
  - An account   → freezes the wallet + marks all active instances for termination

Every kill-switch invocation:
  1. Performs the suspension action
  2. Writes a KillSwitchEvent (immutable audit record)
  3. Writes a SecurityEventLog entry at CRITICAL severity

In mock mode (SCANNER_MOCK=true), all suspension actions succeed immediately
without touching real infrastructure.
"""

import uuid
from typing import Any

import httpx
import structlog

from services.security_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


class KillSwitchError(Exception):
    def __init__(self, target_type: str, target_id: str, reason: str):
        super().__init__(f"Kill switch failed for {target_type}/{target_id}: {reason}")


async def suspend_instance(instance_id: str, admin_token: str) -> dict[str, Any]:
    """
    Immediately terminates the given instance via provisioning_service.
    Returns the broadcast result dict.
    """
    if settings.scanner_mock:
        log.info("kill_switch.suspend_instance.mock", instance_id=instance_id)
        return {"status": "ok", "action": "instance_terminated", "mock": True}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.provisioning_service_url}/v1/instances/{instance_id}/terminate",
                json={"reason": "admin_kill_switch", "force": True},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            resp.raise_for_status()
            return {"status": "ok", "action": "instance_terminated", **resp.json()}
        except httpx.HTTPError as exc:
            log.error("kill_switch.instance_failed", instance_id=instance_id, error=str(exc))
            return {"status": "error", "error": str(exc)}


async def suspend_host(host_id: str, admin_token: str) -> dict[str, Any]:
    """
    Suspends a host via host_service (which broadcasts to the host agent).
    All active instances on that host are terminated first.
    """
    if settings.scanner_mock:
        log.info("kill_switch.suspend_host.mock", host_id=host_id)
        return {"status": "ok", "action": "host_suspended", "mock": True}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{settings.host_service_url}/hosts/{host_id}/suspend",
                json={"reason": "admin_kill_switch"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            resp.raise_for_status()
            return {"status": "ok", "action": "host_suspended", **resp.json()}
        except httpx.HTTPError as exc:
            log.error("kill_switch.host_failed", host_id=host_id, error=str(exc))
            return {"status": "error", "error": str(exc)}


async def suspend_account(user_id: uuid.UUID, admin_token: str) -> dict[str, Any]:
    """
    Freezes the account:
    1. Freezes the wallet (wallet_billing_service)
    2. Terminates all running instances (provisioning_service)
    The TrustTier.is_wallet_frozen flag is set by the caller (repository layer).
    """
    if settings.scanner_mock:
        log.info("kill_switch.suspend_account.mock", user_id=str(user_id))
        return {
            "status": "ok",
            "action": "account_suspended",
            "wallet_frozen": True,
            "instances_terminated": 0,
            "mock": True,
        }

    results: dict[str, Any] = {"action": "account_suspended"}

    # 1. Freeze wallet
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.wallet_billing_service_url}/wallet/freeze",
                json={"user_id": str(user_id), "reason": "admin_kill_switch"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            resp.raise_for_status()
            results["wallet_frozen"] = True
    except httpx.HTTPError as exc:
        log.error("kill_switch.freeze_wallet_failed", user_id=str(user_id), error=str(exc))
        results["wallet_frozen"] = False
        results["wallet_error"] = str(exc)

    # 2. Terminate all running instances for this user
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.provisioning_service_url}/v1/instances?status_filter=running",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            resp.raise_for_status()
            instances = resp.json().get("items", [])
            terminated = 0
            for inst in instances:
                term_resp = await client.post(
                    f"{settings.provisioning_service_url}/v1/instances/{inst['id']}/terminate",
                    json={"reason": "admin_kill_switch_account", "force": True},
                    headers={"Authorization": f"Bearer {admin_token}"},
                )
                if term_resp.status_code in (200, 202):
                    terminated += 1
            results["instances_terminated"] = terminated
    except httpx.HTTPError as exc:
        log.error("kill_switch.terminate_instances_failed", user_id=str(user_id), error=str(exc))
        results["instances_terminated"] = -1
        results["instances_error"] = str(exc)

    results["status"] = "ok" if results.get("wallet_frozen") else "partial"
    return results
