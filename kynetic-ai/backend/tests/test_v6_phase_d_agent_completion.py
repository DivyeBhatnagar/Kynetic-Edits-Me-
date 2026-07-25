"""
Phase D Integration Tests — Host Agent Completion

Tests:
1. Auto-Update Engine: release manifest check, SHA-256 integrity verification, atomic swap & rollback
2. Repeatable Benchmarking Suite & Tolerance Check: FLOPS, LLM inference, Image Gen, Disk I/O, verify_score_tolerance
3. Host Staleness Watcher: timeout detection & listing flagging (60s cutoff)
4. Internal Engineering Host Health API: GET /hosts/{id}/health
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus, OSType, HeartbeatStatus
from libs.db_models.marketplace_models import Listing, ResourceType, ListingStatus
from services.host_service.main import app as host_app
from host_agent.auto_update import AutoUpdateManager
from host_agent.benchmark_runner import (
    run_all_benchmarks,
    run_disk_io_benchmark,
    verify_score_tolerance,
)
from services.host_service.staleness_watcher import check_and_mark_offline_hosts


@pytest.fixture
async def db_override(db_session: AsyncSession):
    async def _override():
        yield db_session

    host_app.dependency_overrides[get_db_session] = _override
    yield db_session
    host_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auto_update_engine(tmp_path: Path):
    target = tmp_path / "kynetic-agent.py"
    target.write_text("print('v1.0.0')")

    # 1. SHA-256 Integrity Verification
    new_content = b"print('v1.0.1')"
    import hashlib
    content_hash = hashlib.sha256(new_content).hexdigest()
    assert AutoUpdateManager.verify_integrity(new_content, content_hash) is True
    assert AutoUpdateManager.verify_integrity(new_content, "wronghash") is False

    # 2. Atomic Swap
    success = AutoUpdateManager.apply_atomic_update(target, new_content)
    assert success is True
    assert target.read_bytes() == new_content

    # 3. Rollback
    rollback_ok = AutoUpdateManager.rollback(target)
    assert rollback_ok is True
    assert target.read_text() == "print('v1.0.0')"


@pytest.mark.asyncio
async def test_repeatable_benchmarking_and_tolerance():
    # Run disk I/O benchmark
    disk_res = run_disk_io_benchmark(duration_seconds=1.0)
    assert disk_res.benchmark_type == "disk_io"
    assert disk_res.score >= 0.0

    # Tolerance verification
    assert verify_score_tolerance(current_score=100.0, baseline_score=100.0) is True
    assert verify_score_tolerance(current_score=90.0, baseline_score=100.0) is True
    assert verify_score_tolerance(current_score=80.0, baseline_score=100.0) is False  # >15% drop


@pytest.mark.asyncio
async def test_host_staleness_watcher(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"stale_{user_id.hex[:6]}@example.com",
        hashed_password="hash",
        role=UserRole.HOST,
    )
    db_session.add(user)

    stale_time = datetime.now(tz=timezone.utc) - timedelta(seconds=120)
    host = Host(
        id=uuid.uuid4(),
        user_id=user_id,
        status=HostStatus.VERIFIED,
        os_type=OSType.LINUX,
        agent_version="1.0.0",
        updated_at=stale_time,
    )
    db_session.add(host)

    listing = Listing(
        id=uuid.uuid4(),
        host_id=host.id,
        owner_user_id=user_id,
        resource_type=ResourceType.gpu,
        gpu_model="NVIDIA RTX 4090",
        gpu_count=1,
        gpu_vram_gb=24.0,
        cpu_cores=16,
        ram_gb=64.0,
        storage_gb=500.0,
        price_per_hour_usd=Decimal("0.50"),
        price_per_hour_inr=Decimal("41.50"),
        price_per_second_usd=Decimal("0.000138"),
        price_per_second_inr=Decimal("0.0115"),
        region="us-east-1",
        status=ListingStatus.active,
    )
    db_session.add(listing)
    await db_session.commit()

    stale_ids = await check_and_mark_offline_hosts(db_session, timeout_seconds=60)
    assert host.id in stale_ids

    # Verify listing paused
    await db_session.refresh(listing)
    assert listing.status == ListingStatus.paused


@pytest.mark.asyncio
async def test_host_health_report_api(db_override: AsyncSession):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"health_{user_id.hex[:6]}@example.com",
        hashed_password="hash",
        role=UserRole.HOST,
    )
    db_override.add(user)

    host = Host(
        id=uuid.uuid4(),
        user_id=user_id,
        status=HostStatus.VERIFIED,
        os_type=OSType.LINUX,
        agent_version="1.0.0",
        spec_verified=True,
        benchmark_verified=True,
    )
    db_override.add(host)
    await db_override.commit()

    async with AsyncClient(transport=ASGITransport(app=host_app), base_url="http://testserver") as client:
        # GET /hosts/agent/releases/latest
        rel_resp = await client.get("/hosts/agent/releases/latest")
        assert rel_resp.status_code == 200
        assert rel_resp.json()["version"] == "1.0.1"

        # GET /hosts/{host_id}/health
        health_resp = await client.get(f"/hosts/{host.id}/health")
        assert health_resp.status_code == 200
        health_data = health_resp.json()
        assert health_data["host_id"] == str(host.id)
        assert health_data["spec_verified"] is True
