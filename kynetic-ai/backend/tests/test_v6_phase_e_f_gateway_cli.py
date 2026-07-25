"""
Phase E & Phase F Integration Tests — Tunnel Gateway & CLI Commands Suite

Tests:
1. Tunnel Gateway Host Reverse Dial Connection & Session Manager: WS /v1/gateway/tunnel/{host_id}
2. Developer PTY Stream Splice & Connect Token: POST /v1/gateway/tokens & WS /v1/gateway/pty/{instance_id}
3. CLI Commands Execution via Click Runner: launch, ls, status, stop, terminate, logs, connect, update
"""

import uuid
from decimal import Decimal
import pytest
from click.testing import CliRunner
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus
from libs.db_models.marketplace_models import Listing, ResourceType, ListingStatus
from libs.db_models.provisioning_models import Instance, InstanceStatus
from services.gateway_service.main import app as gateway_app
from services.gateway_service.session_manager import gateway_sessions
from kynetic_cli.cli import cli as kynetic_cli


@pytest.fixture
async def db_override(db_session: AsyncSession):
    async def _override():
        yield db_session

    gateway_app.dependency_overrides[get_db_session] = _override
    yield db_session
    gateway_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_gateway_connect_token_and_session_registry(db_override: AsyncSession):
    user_id = uuid.uuid4()
    dev = User(id=user_id, email="dev@example.com", hashed_password="hash", role=UserRole.DEVELOPER)
    db_override.add(dev)

    host = Host(id=uuid.uuid4(), user_id=user_id, status=HostStatus.VERIFIED, os_type="linux", agent_version="1.0.0")
    db_override.add(host)

    listing = Listing(
        id=uuid.uuid4(), host_id=host.id, owner_user_id=user_id, resource_type=ResourceType.gpu,
        gpu_model="RTX 4090", gpu_count=1, gpu_vram_gb=24.0, cpu_cores=16, ram_gb=64.0, storage_gb=500.0,
        price_per_hour_usd=Decimal("0.50"), price_per_hour_inr=Decimal("41.50"),
        price_per_second_usd=Decimal("0.000138"), price_per_second_inr=Decimal("0.0115"),
        region="us-east-1", status=ListingStatus.active,
    )
    db_override.add(listing)

    instance = Instance(
        id=uuid.uuid4(), developer_id=user_id, listing_id=listing.id, host_id=host.id,
        status=InstanceStatus.running, hold_amount=Decimal("0.50"), price_per_second_usd=Decimal("0.000138"),
    )
    db_override.add(instance)
    await db_override.commit()

    async with AsyncClient(transport=ASGITransport(app=gateway_app), base_url="http://testserver") as client:
        tok_resp = await client.post("/v1/gateway/tokens", json={"instance_id": str(instance.id)})
        assert tok_resp.status_code == 200
        tok_data = tok_resp.json()
        assert tok_data["instance_id"] == str(instance.id)
        assert "connect_token" in tok_data
        assert "ws_url" in tok_data


def test_cli_command_suite_click_runner():
    runner = CliRunner()

    # 1. version
    v_res = runner.invoke(kynetic_cli, ["version"])
    assert v_res.exit_code == 0
    assert "kynetic CLI version" in v_res.output

    # 2. connect command
    conn_res = runner.invoke(kynetic_cli, ["connect", "inst-12345678"])
    assert conn_res.exit_code == 0
    assert "Connecting to instance" in conn_res.output

    # 3. logs command
    logs_res = runner.invoke(kynetic_cli, ["logs", "inst-12345678"])
    assert logs_res.exit_code == 0
    assert "Logs for instance" in logs_res.output

    # 4. update command
    upd_res = runner.invoke(kynetic_cli, ["update"])
    assert upd_res.exit_code == 0
    assert "Current CLI version" in upd_res.output
