"""
Backend/tests/test_v8_feature_4_5_6_search_launch.py

Comprehensive Pytest suite for v8 Features 4, 5, 6 & 7:
- Feature 4: GPU Benchmark Database & Analytics Engine
- Feature 5: Smart Search Engine
- Feature 6: One Command Launch CLI
- Feature 7: System Integration & Synthesis
"""

import uuid
from decimal import Decimal

import pytest
from click.testing import CliRunner
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from kynetic_cli.cli import cli
from libs.db_models.host_models import Host, OSType
from libs.db_models.marketplace_models import Listing, ListingStatus, ResourceType, SearchableListing
from libs.db_models.reputation_pricing_models import HostBenchmarkRun, HostScore, ReputationScore
from libs.db_models.user_models import User, UserRole
from services.marketplace_service.main import app as marketplace_app
from services.marketplace_service.search_engine import execute_smart_search, sync_all_searchable_listings, sync_searchable_listing
from services.reputation_pricing_service.benchmark_analytics import compare_gpu_models, get_gpu_model_summaries, get_price_performance_rankings, refresh_gpu_benchmark_analytics


@pytest.mark.asyncio
async def test_refresh_gpu_benchmark_analytics(db_session: AsyncSession):
    # Setup test host & benchmark runs
    user_id = uuid.uuid4()
    user = User(id=user_id, email="analytics_user@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    run_id = uuid.uuid4()
    run1 = HostBenchmarkRun(
        host_id=host_id,
        run_id=run_id,
        gpu_model="NVIDIA RTX 4090",
        benchmark_type="gpu_fp16_tflops",
        value=82.5,
        unit="TFLOPS",
        flag_status="ok",
    )
    run2 = HostBenchmarkRun(
        host_id=host_id,
        run_id=run_id,
        gpu_model="NVIDIA RTX 4090",
        benchmark_type="gpu_mem_bandwidth_gbps",
        value=1008.0,
        unit="GB/s",
        flag_status="ok",
    )
    db_session.add_all([run1, run2])

    listing = Listing(
        host_id=host_id,
        owner_user_id=user_id,
        resource_type=ResourceType.gpu,
        gpu_model="NVIDIA RTX 4090",
        price_per_hour_usd=Decimal("0.45"),
        price_per_hour_inr=Decimal("37.50"),
        price_per_second_usd=Decimal("0.000125"),
        price_per_second_inr=Decimal("0.0104"),
        status=ListingStatus.active,
    )
    db_session.add(listing)

    host_score = HostScore(
        host_id=host_id,
        performance_score=0.88,
        health_score=0.95,
        composite_score=0.90,
    )
    db_session.add(host_score)
    await db_session.commit()

    res = await refresh_gpu_benchmark_analytics(db_session)
    await db_session.commit()

    assert res["gpu_model_stats"] >= 1
    assert res["price_performance_stats"] >= 1

    summaries = await get_gpu_model_summaries(db_session, model="NVIDIA RTX 4090")
    assert len(summaries) == 1
    assert summaries[0]["gpu_model"] == "NVIDIA RTX 4090"
    assert summaries[0]["avg_tensor_fp16_tflops"] == 82.5

    rankings = await get_price_performance_rankings(db_session)
    assert len(rankings) >= 1
    assert rankings[0]["gpu_model"] == "NVIDIA RTX 4090"
    assert rankings[0]["price_performance_ratio"] > 0


@pytest.mark.asyncio
async def test_compare_gpu_models(db_session: AsyncSession):
    comp = await compare_gpu_models(db_session, "NVIDIA RTX 4090", "NVIDIA RTX 3090")
    assert comp["model_a"] == "NVIDIA RTX 4090"
    assert comp["model_b"] == "NVIDIA RTX 3090"


@pytest.mark.asyncio
async def test_sync_searchable_listing_and_smart_search(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="search_user@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, os_type=OSType.LINUX, agent_version="1.0.0", verification_level="gold")
    db_session.add(host)
    await db_session.commit()

    listing_id = uuid.uuid4()
    listing = Listing(
        id=listing_id,
        host_id=host_id,
        owner_user_id=user_id,
        resource_type=ResourceType.gpu,
        gpu_model="NVIDIA A100-SXM4-80GB",
        gpu_vram_gb=Decimal("80.0"),
        cpu_cores=64,
        ram_gb=Decimal("256.0"),
        price_per_hour_usd=Decimal("1.85"),
        price_per_hour_inr=Decimal("150.00"),
        price_per_second_usd=Decimal("0.0005138"),
        price_per_second_inr=Decimal("0.0416"),
        region="us-east",
        status=ListingStatus.active,
    )
    db_session.add(listing)

    host_score = HostScore(
        host_id=host_id,
        performance_score=0.96,
        health_score=0.98,
        composite_score=0.97,
    )
    rep_score = ReputationScore(
        host_id=host_id,
        composite_score=0.88,
    )
    db_session.add_all([host_score, rep_score])
    await db_session.commit()

    synced = await sync_searchable_listing(db_session, listing_id)
    await db_session.commit()

    assert synced is not None
    assert synced.gpu_model == "NVIDIA A100-SXM4-80GB"
    assert synced.verification_level == "gold"
    assert float(synced.price_per_hour_usd) == 1.85

    # Execute smart search query
    results = await execute_smart_search(
        db_session,
        filters={
            "gpu_model": "NVIDIA A100-SXM4-80GB",
            "min_vram": 40.0,
            "verification_level": "gold",
            "max_price": 2.00,
            "sort": "value",
        },
    )

    assert len(results) == 1
    assert results[0]["listing_id"] == str(listing_id)
    assert results[0]["verification_level"] == "gold"


@pytest.mark.asyncio
async def test_smart_search_api_routes(db_session: AsyncSession):
    transport = ASGITransport(app=marketplace_app)

    async def _override_get_db_session():
        yield db_session

    from libs.db_models.database import get_db_session
    marketplace_app.dependency_overrides[get_db_session] = _override_get_db_session

    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp_sync = await ac.post("/search/sync")
        assert resp_sync.status_code == 200

        resp_search = await ac.get("/search/listings?sort=value")
        assert resp_search.status_code == 200

        resp_bench = await ac.get("/benchmarks/gpu-models")
        assert resp_bench.status_code == 200

        resp_pp = await ac.get("/benchmarks/price-performance")
        assert resp_pp.status_code == 200

    marketplace_app.dependency_overrides.clear()


def test_cli_one_command_launch_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["launch", "--help"])
    assert result.exit_code == 0
    assert "One-command launch" in result.output
    assert "--gpu" in result.output
    assert "--yes" in result.output
    assert "--resume" in result.output
