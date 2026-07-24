"""
Phase 32 Unit Tests — Host Agent Provisioning Engine & Protocol.

Tests:
  - AgentProtocol client methods (provision, stop, terminate, delete_volume, verify_deletion)
  - Mock mode vs HTTP calls
  - Error propagation on network failures
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import httpx

from services.provisioning_service.agent_protocol import AgentProtocol


@pytest.mark.asyncio
async def test_agent_protocol_mock_provision():
    instance_id = uuid.uuid4()
    agent = AgentProtocol("mock://agent", instance_id)

    res = await agent.provision(
        public_key="ssh-rsa AAA...",
        wireguard_config="[Interface]...",
        price_per_second_usd="0.000277",
    )

    assert res["status"] == "ok"
    assert "firecracker_vm_id" in res
    assert "container_id" in res


@pytest.mark.asyncio
async def test_agent_protocol_mock_stop_and_terminate():
    instance_id = uuid.uuid4()
    agent = AgentProtocol("mock://agent", instance_id)

    stop_res = await agent.stop()
    assert stop_res["status"] == "ok"
    assert stop_res["event"] == "stopped"

    term_res = await agent.terminate()
    assert term_res["status"] == "ok"
    assert term_res["event"] == "terminated"


@pytest.mark.asyncio
async def test_agent_protocol_mock_volume_shred_and_verify():
    instance_id = uuid.uuid4()
    agent = AgentProtocol("mock://agent", instance_id)

    shred_res = await agent.delete_volume()
    assert shred_res["status"] == "ok"
    assert "confirmation_hash" in shred_res

    verify_res = await agent.verify_deletion()
    assert verify_res["status"] == "ok"
    assert verify_res["confirmation_hash"] == shred_res["confirmation_hash"]


@pytest.mark.asyncio
async def test_agent_protocol_http_error_handling():
    """Verify that httpx HTTP errors propagate on network failure when mock is disabled."""
    instance_id = uuid.uuid4()
    agent = AgentProtocol("http://192.168.1.50:8443", instance_id)

    mock_settings = type("Settings", (), {
        "firecracker_mock": False,
        "mtls_client_cert_path": "/certs/client.crt",
        "mtls_client_key_path": "/certs/client.key",
        "mtls_ca_cert_path": "/certs/ca.crt",
    })()

    with patch("services.provisioning_service.agent_protocol.get_settings", return_value=mock_settings):
        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")):
            with pytest.raises(httpx.ConnectError):
                await agent.provision(
                    public_key="ssh-rsa AAA...",
                    wireguard_config="[Interface]...",
                    price_per_second_usd="0.000277",
                )
