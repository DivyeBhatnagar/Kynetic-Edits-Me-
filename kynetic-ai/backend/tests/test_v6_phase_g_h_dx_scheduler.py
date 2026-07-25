"""
Phase G & Phase H Integration Tests — Developer Experience & Weighted Scheduler

Tests:
1. Chunked File Transfer & Checksum: FileTransferClient.upload_file & compute_file_checksum
2. VS Code Remote SSH Config Injection & Port Forwarding: TunnelManager.generate_ssh_config & create_port_forward
3. Host Reputation Calculator & Dashboard API: ReputationCalculator & GET /hosts/{id}/dashboard
4. Weighted 6-Factor Scheduler Ranking Algorithm: rank_hosts_6factor (balanced, budget, fastest)
"""

import uuid
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus
from services.host_service.main import app as host_app
from kynetic_cli.file_transfer import FileTransferClient
from kynetic_cli.tunnel_manager import TunnelManager
from services.host_service.reputation_service import ReputationCalculator
from services.provisioning_service.scheduler import rank_hosts_6factor


@pytest.fixture
async def db_override(db_session: AsyncSession):
    async def _override():
        yield db_session

    host_app.dependency_overrides[get_db_session] = _override
    yield db_session
    host_app.dependency_overrides.clear()


def test_file_transfer_checksum_and_upload(tmp_path: Path):
    test_file = tmp_path / "model.pt"
    test_file.write_bytes(b"0" * (2 * 1024 * 1024))  # 2MB file

    client = FileTransferClient()
    file_hash = client.compute_file_checksum(test_file)
    assert len(file_hash) == 64

    res = client.upload_file("inst-123", str(test_file), "/workspace/model.pt")
    assert res["status"] == "completed"
    assert res["chunks_transferred"] == 2
    assert res["sha256_hash"] == file_hash


def test_tunnel_manager_ssh_config_and_port_forward(tmp_path: Path):
    ssh_cfg = tmp_path / "ssh_config"

    alias = TunnelManager.generate_ssh_config(
        instance_id="abc12345678",
        ssh_host="10.42.0.5",
        ssh_port=2222,
        identity_file="/keys/key.pem",
        ssh_config_path=ssh_cfg,
    )
    assert alias == "kynetic-abc12345"
    assert "Host kynetic-abc12345" in ssh_cfg.read_text()
    assert "HostName 10.42.0.5" in ssh_cfg.read_text()

    local_fwd = TunnelManager.create_port_forward("abc12345", 8080, 8080, is_public=False)
    assert local_fwd["type"] == "local"

    pub_fwd = TunnelManager.create_port_forward("abc12345", 8080, 8080, is_public=True)
    assert pub_fwd["type"] == "public"


def test_reputation_calculator():
    score = ReputationCalculator.calculate_score(
        uptime_pct=100.0,
        benchmark_consistency_pct=100.0,
        completion_rate_pct=100.0,
        days_verified=30,
    )
    assert score == 100.0

    degraded_score = ReputationCalculator.calculate_score(
        uptime_pct=50.0,
        benchmark_consistency_pct=50.0,
        completion_rate_pct=50.0,
        days_verified=10,
    )
    assert degraded_score < 100.0


def test_6factor_weighted_scheduler_ranking():
    candidates = [
        {"host_id": "h1", "price_score": 0.5, "benchmark_score": 0.9, "reputation_score": 95.0, "is_available": True},
        {"host_id": "h2", "price_score": 0.9, "benchmark_score": 0.4, "reputation_score": 70.0, "is_available": True},
    ]

    # Budget preference -> h2 (higher price score) should rank higher
    ranked_budget = rank_hosts_6factor(candidates, preference="budget")
    assert ranked_budget[0]["host_id"] == "h2"

    # Fastest preference -> h1 (higher benchmark score) should rank higher
    ranked_fastest = rank_hosts_6factor(candidates, preference="fastest")
    assert ranked_fastest[0]["host_id"] == "h1"


@pytest.mark.asyncio
async def test_host_dashboard_api(db_override: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="dash@example.com", hashed_password="hash", role=UserRole.HOST)
    db_override.add(user)

    host = Host(id=uuid.uuid4(), user_id=user_id, status=HostStatus.VERIFIED, os_type="linux", agent_version="1.0.0", benchmark_verified=True)
    db_override.add(host)
    await db_override.commit()

    async with AsyncClient(transport=ASGITransport(app=host_app), base_url="http://testserver") as client:
        dash_resp = await client.get(f"/hosts/{host.id}/dashboard")
        assert dash_resp.status_code == 200
        data = dash_resp.json()
        assert data["host_id"] == str(host.id)
        assert "reputation_score" in data
        assert "total_earnings_usd" in data
