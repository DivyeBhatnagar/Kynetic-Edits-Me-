"""
Phase B Integration Tests — Host Onboarding & Marketplace

Tests:
1. Host Registration: POST /hosts/register
2. Hardware Spec Snapshotting: machines, gpus, cpu_specs, ram_specs, storage_specs
3. Benchmark Submission & Verification: POST /hosts/{id}/benchmarks
4. Host State Machine Transitions: pending_verification -> benchmarking -> verified
5. Marketplace Search & Filtering: GET /listings (GPU model, VRAM, price, region)
6. Heartbeat Telemetry: POST /hosts/heartbeat
"""

import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus
from libs.db_models.marketplace_models import Listing, ResourceType, ListingStatus
from services.host_service.main import app as host_app
from services.marketplace_service.main import app as marketplace_app


from libs.common.auth import require_auth
from services.host_service.routes import get_current_user_id


@pytest.fixture
async def db_override(db_session: AsyncSession, test_user_and_token):
    user, _ = test_user_and_token
    async def _override():
        yield db_session

    host_app.dependency_overrides[get_db_session] = _override
    host_app.dependency_overrides[require_auth] = lambda: {"sub": str(user.id), "role": "host"}
    host_app.dependency_overrides[get_current_user_id] = lambda: user.id
    marketplace_app.dependency_overrides[get_db_session] = _override
    marketplace_app.dependency_overrides[require_auth] = lambda: {"sub": str(user.id), "role": "host"}
    marketplace_app.dependency_overrides[get_current_user_id] = lambda: user.id
    yield db_session
    host_app.dependency_overrides.clear()
    marketplace_app.dependency_overrides.clear()


@pytest.fixture
async def test_user_and_token(db_session: AsyncSession):
    """Create test user and return (user, access_token)."""
    from services.auth_service.security import create_access_token
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        email=f"host_user_{user_id.hex[:6]}@example.com",
        hashed_password="$2b$12$eImiTXuWVxfM37uY4JANjO5E/8G5e2j9Y3v.3mK9W6iJz/jE2j5hS",
        role=UserRole.HOST,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    access_token = create_access_token(user_id=user.id, role=user.role.value)
    return user, access_token


@pytest.mark.asyncio
async def test_host_registration_flow(test_user_and_token, db_override: AsyncSession):
    user, access_token = test_user_and_token
    agent_id = uuid.uuid4()

    payload = {
        "agent_id": str(agent_id),
        "agent_version": "1.0.0",
        "os_type": "linux",
        "hardware": {
            "cpu_model": "AMD EPYC 7763 64-Core Processor",
            "cpu_cores": 32,
            "cpu_threads": 64,
            "ram_gb": 128.0,
            "disk_type": "nvme",
            "disk_gb": 1000.0,
            "gpu_model": "NVIDIA RTX 4090",
            "gpu_count": 2,
            "gpu_vram_gb": 24.0,
            "driver_version": "535.104.05",
            "cuda_version": "12.2",
            "temperature_c": 45.0,
            "power_draw_w": 250.0,
            "raw_spec": {"test": True},
        },
    }

    headers = {"Authorization": f"Bearer {access_token}"}
    async with AsyncClient(transport=ASGITransport(app=host_app), base_url="http://testserver") as client:
        resp = await client.post("/hosts/register", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert "host_id" in data
        assert data["status"] == "benchmarking"
        assert "mtls_client_cert_pem" in data

        host_id = uuid.UUID(data["host_id"])

        # Fetch host directly from DB to verify hardware specs
        host = await db_override.get(Host, host_id)
        assert host is not None
        assert host.user_id == user.id
        assert host.status == HostStatus.BENCHMARKING
        assert host.spec_verified is True


@pytest.mark.asyncio
async def test_host_benchmark_submission_and_verification(test_user_and_token, db_override: AsyncSession):
    user, access_token = test_user_and_token
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Register host
    reg_payload = {
        "agent_id": str(uuid.uuid4()),
        "agent_version": "1.0.0",
        "os_type": "linux",
        "hardware": {
            "cpu_cores": 16,
            "cpu_threads": 32,
            "ram_gb": 64.0,
            "disk_type": "nvme",
            "disk_gb": 500.0,
            "gpu_model": "NVIDIA H100",
            "gpu_count": 1,
            "gpu_vram_gb": 80.0,
        },
    }

    async with AsyncClient(transport=ASGITransport(app=host_app), base_url="http://testserver") as client:
        resp = await client.post("/hosts/register", json=reg_payload, headers=headers)
        assert resp.status_code == 201
        host_id = resp.json()["host_id"]

        # 2. Submit benchmark results
        bench_payload = {
            "host_id": host_id,
            "results": [
                {
                    "benchmark_type": "llm_inference",
                    "score": 120.5,
                    "raw_metrics": {"tokens_per_sec": 120.5},
                },
                {
                    "benchmark_type": "image_gen",
                    "score": 25.4,
                    "raw_metrics": {"steps_per_sec": 25.4},
                },
                {
                    "benchmark_type": "flops",
                    "score": 68.2,
                    "raw_metrics": {"tflops": 68.2},
                },
            ],
        }

        resp_bench = await client.post(
            f"/hosts/{host_id}/benchmarks", json=bench_payload, headers=headers
        )
        assert resp_bench.status_code == 200, resp_bench.text
        bench_data = resp_bench.json()
        assert bench_data["all_passed"] is True
        assert bench_data["host_status"] == "verified"

        # 3. GET /hosts/{host_id}
        resp_get = await client.get(f"/hosts/{host_id}", headers=headers)
        assert resp_get.status_code == 200
        host_detail = resp_get.json()
        assert host_detail["status"] == "verified"
        assert host_detail["benchmark_verified"] is True


@pytest.mark.asyncio
async def test_marketplace_listing_search_and_discovery(test_user_and_token, db_override: AsyncSession):
    user, access_token = test_user_and_token

    # 1. Register host
    host = Host(
        id=uuid.uuid4(),
        user_id=user.id,
        status=HostStatus.VERIFIED,
        os_type="linux",
        agent_version="1.0.0",
        spec_verified=True,
        benchmark_verified=True,
    )
    db_override.add(host)

    # 2. Create listing directly in DB for testing search filters
    listing = Listing(
        host_id=host.id,
        owner_user_id=user.id,
        resource_type=ResourceType.gpu,
        gpu_model="NVIDIA RTX 3090",
        gpu_count=1,
        gpu_vram_gb=24.0,
        cpu_cores=8,
        ram_gb=32.0,
        storage_gb=256.0,
        storage_type="ssd",
        price_per_hour_usd=Decimal("0.450000"),
        price_per_hour_inr=Decimal("37.350000"),
        price_per_second_usd=Decimal("0.0001250000"),
        price_per_second_inr=Decimal("0.0103750000"),
        region="us-east-1",
        status=ListingStatus.active,
        title="Fast RTX 3090 24GB Node",
    )
    db_override.add(listing)
    await db_override.commit()

    # 3. GET /listings with search parameters
    async with AsyncClient(transport=ASGITransport(app=marketplace_app), base_url="http://testserver") as client:
        search_resp = await client.get(
            "/listings",
            params={
                "gpu_model": "NVIDIA RTX 3090",
                "max_price_usd": 1.0,
                "region": "us-east-1",
            },
        )
        assert search_resp.status_code == 200, search_resp.text
        search_data = search_resp.json()
        assert "items" in search_data
        assert search_data["total"] >= 1

        match = search_data["items"][0]
        assert match["gpu_model"] == "NVIDIA RTX 3090"
        assert float(match["price_per_hour_usd"]) == 0.45


@pytest.mark.asyncio
async def test_host_heartbeat_telemetry(test_user_and_token, db_override: AsyncSession):
    user, access_token = test_user_and_token
    headers = {"Authorization": f"Bearer {access_token}"}

    async with AsyncClient(transport=ASGITransport(app=host_app), base_url="http://testserver") as client:
        # Register host
        reg_payload = {
            "agent_id": str(uuid.uuid4()),
            "agent_version": "1.0.0",
            "os_type": "linux",
            "hardware": {
                "cpu_cores": 4,
                "cpu_threads": 8,
                "ram_gb": 16.0,
                "disk_type": "ssd",
                "disk_gb": 120.0,
            },
        }
        reg_resp = await client.post("/hosts/register", json=reg_payload, headers=headers)
        host_id = reg_resp.json()["host_id"]

        # Send heartbeat
        hb_payload = {
            "host_id": host_id,
            "status": "idle",
            "temperature_c": 38.5,
            "power_draw_w": 85.0,
            "gpu_utilization_pct": 0.0,
            "ram_used_gb": 4.2,
        }

        hb_resp = await client.post("/hosts/heartbeat", json=hb_payload)
        assert hb_resp.status_code == 200, hb_resp.text
        assert hb_resp.json()["received"] is True
