"""
Provisioning Service — Host Agent mTLS Protocol Client.

Wraps all communication with the Host Agent (running on the host machine)
over mutual TLS. Every method has a mock implementation that activates
when FIRECRACKER_MOCK=true — allowing full service testing on macOS.

Commands sent to agent:
  POST /agent/provision      — create Firecracker VM + Docker container
  POST /agent/stop           — suspend VM
  POST /agent/terminate      — destroy container + VM
  POST /agent/delete_volume  — cryptographic NVMe shred
  GET  /agent/verify_deletion — confirm deletion receipt
"""

import hashlib
import json
import uuid
from typing import Any

import httpx
import structlog

from services.provisioning_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


# ── Mock responses ─────────────────────────────────────────────────────────

def _mock_provision_response(instance_id: uuid.UUID, public_key: str) -> dict:
    return {
        "status": "ok",
        "firecracker_vm_id": f"fc-{str(instance_id)[:8]}",
        "container_id": f"docker-{str(instance_id)[:12]}",
        "event": "provisioning_complete",
    }


def _mock_stop_response(instance_id: uuid.UUID) -> dict:
    return {"status": "ok", "event": "stopped"}


def _mock_terminate_response(instance_id: uuid.UUID) -> dict:
    return {"status": "ok", "event": "terminated"}


def _mock_deletion_response(instance_id: uuid.UUID) -> dict:
    payload = json.dumps({"instance_id": str(instance_id), "method": "mock_shred"})
    confirmation_hash = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "status": "ok",
        "method": "mock_shred",
        "confirmation_hash": confirmation_hash,
        "payload": payload,
    }


# ── mTLS Client factory ────────────────────────────────────────────────────

def _make_mtls_client(agent_host_url: str) -> httpx.AsyncClient:
    """
    Creates an httpx client with mTLS configured.
    In mock mode, returns a client without cert verification
    (since there's no real agent to connect to).
    """
    if settings.firecracker_mock:
        return httpx.AsyncClient(base_url=agent_host_url, timeout=30.0)

    return httpx.AsyncClient(
        base_url=agent_host_url,
        timeout=60.0,
        cert=(settings.mtls_client_cert_path, settings.mtls_client_key_path),
        verify=settings.mtls_ca_cert_path,
    )


# ── Agent protocol ─────────────────────────────────────────────────────────

class AgentProtocol:
    """
    Thin protocol layer over the host agent's HTTP API.
    All methods are async and raise httpx.HTTPError on network failures.
    """

    def __init__(self, agent_host_url: str, instance_id: uuid.UUID):
        self._url = agent_host_url
        self._instance_id = instance_id

    async def provision(
        self,
        *,
        public_key: str,
        wireguard_config: str,
        price_per_second_usd: str,
    ) -> dict[str, Any]:
        """
        Instructs the agent to create a Firecracker microVM + Docker container,
        inject the SSH public key, configure WireGuard, and allocate ephemeral storage.
        """
        if settings.firecracker_mock:
            log.info("agent_protocol.provision.mock", instance_id=str(self._instance_id))
            return _mock_provision_response(self._instance_id, public_key)

        async with _make_mtls_client(self._url) as client:
            resp = await client.post(
                "/agent/provision",
                json={
                    "instance_id": str(self._instance_id),
                    "public_key": public_key,
                    "wireguard_config": wireguard_config,
                    "price_per_second_usd": price_per_second_usd,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def stop(self) -> dict[str, Any]:
        """Suspend the Firecracker microVM (billing pauses)."""
        if settings.firecracker_mock:
            log.info("agent_protocol.stop.mock", instance_id=str(self._instance_id))
            return _mock_stop_response(self._instance_id)

        async with _make_mtls_client(self._url) as client:
            resp = await client.post(
                "/agent/stop",
                json={"instance_id": str(self._instance_id)},
            )
            resp.raise_for_status()
            return resp.json()

    async def terminate(self) -> dict[str, Any]:
        """Destroy the container and microVM."""
        if settings.firecracker_mock:
            log.info("agent_protocol.terminate.mock", instance_id=str(self._instance_id))
            return _mock_terminate_response(self._instance_id)

        async with _make_mtls_client(self._url) as client:
            resp = await client.post(
                "/agent/terminate",
                json={"instance_id": str(self._instance_id)},
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_volume(self) -> dict[str, Any]:
        """
        Cryptographically shred the ephemeral NVMe volume.
        In production: LUKS key destruction + optional DoD overwrite.
        Must be called AFTER terminate().
        """
        if settings.firecracker_mock:
            log.info("agent_protocol.delete_volume.mock", instance_id=str(self._instance_id))
            return _mock_deletion_response(self._instance_id)

        async with _make_mtls_client(self._url) as client:
            resp = await client.post(
                "/agent/delete_volume",
                json={"instance_id": str(self._instance_id)},
            )
            resp.raise_for_status()
            return resp.json()

    async def verify_deletion(self) -> dict[str, Any]:
        """
        Fetches the deletion confirmation receipt from the agent.
        The provisioning service stores this receipt before marking
        the instance as terminated.
        """
        if settings.firecracker_mock:
            log.info("agent_protocol.verify_deletion.mock", instance_id=str(self._instance_id))
            return _mock_deletion_response(self._instance_id)

        async with _make_mtls_client(self._url) as client:
            resp = await client.get(
                "/agent/verify_deletion",
                params={"instance_id": str(self._instance_id)},
            )
            resp.raise_for_status()
            return resp.json()
