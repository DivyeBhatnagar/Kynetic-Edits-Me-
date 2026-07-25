"""
v8 Feature 1 Tests — GPU Benchmark & Health Score.

Tests:
1. Unit: Min-max normalisation & CV stability score calculation
2. Unit: Envelope check fraud detection (under/over expected hardware range)
3. Unit: Performance score peer-group normalisation & missing telemetry handling
4. Unit: Health score thermal/clock/power stability calculation
5. Unit: Composite score computation
6. Integration: POST /v1/hosts/{id}/benchmarks/run ingestion & envelope flagging
7. Integration: GET /v1/hosts/{id}/scores & GET /v1/hosts/{id}/benchmarks/history endpoints
"""

import uuid
from datetime import UTC, datetime
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import libs.db_models  # noqa: F401
from libs.db_models.database import get_db_session
from libs.db_models.host_models import Host, HostStatus
from libs.db_models.user_models import User, UserRole
from services.reputation_pricing_service.benchmark_suite import (
    BenchmarkRunInput,
    HeartbeatSample,
    PeerEnvelope,
    _cv_to_stability,
    _minmax_normalise,
    check_envelope,
    compute_health_score,
    compute_host_composite,
    compute_performance_score,
)
from services.reputation_pricing_service.main import app as rep_app


# ── 1. Unit Tests for Benchmark Suite Engine ─────────────────────────────────

def test_minmax_normalise():
    assert _minmax_normalise(50, 0, 100) == 0.5
    assert _minmax_normalise(0, 0, 100) == 0.0
    assert _minmax_normalise(100, 0, 100) == 1.0
    assert _minmax_normalise(150, 0, 100) == 1.0  # clamped max
    assert _minmax_normalise(-10, 0, 100) == 0.0  # clamped min
    assert _minmax_normalise(50, 50, 50) == 1.0   # single sample / degenerate range


def test_cv_to_stability():
    # Perfectly constant telemetry -> CV = 0 -> stability = 1.0
    assert _cv_to_stability([70.0, 70.0, 70.0, 70.0]) == 1.0

    # Highly variable telemetry -> CV >= 0.20 -> stability = 0.0
    assert _cv_to_stability([10.0, 50.0, 100.0]) == 0.0

    # Insufficient samples (< 3) -> None
    assert _cv_to_stability([70.0, 72.0]) is None


def test_check_envelope():
    env = PeerEnvelope(
        gpu_model="RTX 4090",
        benchmark_type="gpu_fp16_tflops",
        min_value=70.0,
        max_value=95.0,
        unit="TFLOPS",
    )

    # Valid run within range
    valid_run = BenchmarkRunInput(benchmark_type="gpu_fp16_tflops", value=82.5, unit="TFLOPS")
    assert check_envelope(valid_run, env) is None

    # Below minimum -> flagged
    low_run = BenchmarkRunInput(benchmark_type="gpu_fp16_tflops", value=45.0, unit="TFLOPS")
    flag_low = check_envelope(low_run, env)
    assert flag_low is not None
    assert flag_low.severity == "flagged"
    assert "below" in flag_low.reason

    # Above maximum (spoofed) -> flagged
    high_run = BenchmarkRunInput(benchmark_type="gpu_fp16_tflops", value=200.0, unit="TFLOPS")
    flag_high = check_envelope(high_run, env)
    assert flag_high is not None
    assert flag_high.severity == "flagged"
    assert "exceeds" in flag_high.reason

    # No envelope defined for metric -> accepted (None)
    assert check_envelope(valid_run, None) is None


def test_compute_performance_score():
    runs = [
        BenchmarkRunInput(benchmark_type="gpu_fp16_tflops", value=80.0, unit="TFLOPS"),
        BenchmarkRunInput(benchmark_type="gpu_fp32_tflops", value=40.0, unit="TFLOPS"),
        BenchmarkRunInput(benchmark_type="gpu_mem_bandwidth_gbps", value=1000.0, unit="GB/s"),
    ]

    envelopes = {
        "gpu_fp16_tflops": PeerEnvelope(
            gpu_model="RTX 4090", benchmark_type="gpu_fp16_tflops",
            min_value=60.0, max_value=100.0, unit="TFLOPS", peer_min=60.0, peer_max=100.0, peer_count=5
        ),
        "gpu_fp32_tflops": PeerEnvelope(
            gpu_model="RTX 4090", benchmark_type="gpu_fp32_tflops",
            min_value=30.0, max_value=50.0, unit="TFLOPS", peer_min=30.0, peer_max=50.0, peer_count=5
        ),
        "gpu_mem_bandwidth_gbps": PeerEnvelope(
            gpu_model="RTX 4090", benchmark_type="gpu_mem_bandwidth_gbps",
            min_value=800.0, max_value=1200.0, unit="GB/s", peer_min=800.0, peer_max=1200.0, peer_count=5
        ),
    }

    res = compute_performance_score(runs, envelopes)
    assert res.performance_score is not None
    assert pytest.approx(res.fp16_tflops_normalised, 0.01) == 0.5   # (80-60)/(100-60)
    assert pytest.approx(res.fp32_tflops_normalised, 0.01) == 0.5   # (40-30)/(50-30)
    assert pytest.approx(res.mem_bandwidth_normalised, 0.01) == 0.5 # (1000-800)/(1200-800)
    assert pytest.approx(res.performance_score, 0.01) == 0.5
    assert res.peer_group_size == 5
    assert len(res.flags) == 0


def test_compute_performance_score_missing_data():
    # Only 1 of 3 metrics provided -> composite should re-normalise weights
    runs = [
        BenchmarkRunInput(benchmark_type="gpu_fp16_tflops", value=80.0, unit="TFLOPS"),
    ]
    envelopes = {
        "gpu_fp16_tflops": PeerEnvelope(
            gpu_model="RTX 4090", benchmark_type="gpu_fp16_tflops",
            min_value=60.0, max_value=100.0, unit="TFLOPS", peer_min=60.0, peer_max=100.0, peer_count=1
        ),
    }
    res = compute_performance_score(runs, envelopes)
    assert res.performance_score is not None
    assert pytest.approx(res.performance_score, 0.01) == 0.5
    assert res.fp32_tflops_normalised is None
    assert res.mem_bandwidth_normalised is None


def test_compute_health_score():
    # Stable heatbeats
    samples = [
        HeartbeatSample(gpu_temperature_celsius=65.0, cpu_temperature_celsius=50.0, power_draw_watts=250.0, gpu_core_clock_mhz=2500.0),
        HeartbeatSample(gpu_temperature_celsius=66.0, cpu_temperature_celsius=51.0, power_draw_watts=252.0, gpu_core_clock_mhz=2505.0),
        HeartbeatSample(gpu_temperature_celsius=65.5, cpu_temperature_celsius=50.5, power_draw_watts=251.0, gpu_core_clock_mhz=2502.0),
    ]

    res = compute_health_score(samples)
    assert res.health_score is not None
    assert res.health_score > 0.90
    assert res.thermal_stability_score is not None
    assert res.clock_stability_score is not None
    assert res.power_stability_score is not None
    assert res.samples_used == 3


def test_compute_host_composite():
    comp = compute_host_composite(
        performance_score=0.80,
        health_score=0.90,
        reliability_score=1.00,
    )
    # Weights: perf 0.50, health 0.30, reliability 0.20 -> 0.40 + 0.27 + 0.20 = 0.87
    assert comp is not None
    assert pytest.approx(comp, 0.01) == 0.87

    # Missing performance score -> re-normalised
    partial = compute_host_composite(
        performance_score=None,
        health_score=0.80,
        reliability_score=1.00,
    )
    # Weights: health 0.30 / 0.50, reliability 0.20 / 0.50 -> 0.6*0.80 + 0.4*1.00 = 0.88
    assert partial is not None
    assert pytest.approx(partial, 0.01) == 0.88


# ── 2. Integration Tests for API Endpoints ───────────────────────────────────

@pytest.fixture
async def rep_client(db_session: AsyncSession) -> AsyncClient:
    async def _override():
        yield db_session

    rep_app.dependency_overrides[get_db_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=rep_app),
        base_url="http://testserver",
    ) as client:
        yield client
    rep_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_v8_benchmark_run_scores_history_e2e(db_session: AsyncSession, rep_client: AsyncClient):
    # 1. Create a host
    user_id = uuid.uuid4()
    user = User(id=user_id, email="v8host@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(
        id=host_id,
        user_id=user_id,
        status=HostStatus.VERIFIED,
        os_type="linux",
        agent_version="1.0.0",
    )
    db_session.add(host)
    await db_session.commit()

    # 2. Trigger benchmark run (POST /v1/hosts/{id}/benchmarks/run)
    run_resp = await rep_client.post(
        f"/v1/hosts/{host_id}/benchmarks/run",
        json={
            "gpu_model": "RTX 4090",
            "cuda_version": "12.2",
            "driver_version": "535.104",
            "sub_tests": [
                {"benchmark_type": "gpu_fp16_tflops", "value": 82.5, "unit": "TFLOPS"},
                {"benchmark_type": "gpu_fp32_tflops", "value": 41.2, "unit": "TFLOPS"},
                {"benchmark_type": "gpu_mem_bandwidth_gbps", "value": 1008.0, "unit": "GB/s"},
            ]
        }
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["host_id"] == str(host_id)
    assert run_data["sub_tests_run"] == 3
    assert run_data["status"] == "completed"

    # 3. Get computed scores (GET /v1/hosts/{id}/scores)
    scores_resp = await rep_client.get(f"/v1/hosts/{host_id}/scores")
    assert scores_resp.status_code == 200
    scores_data = scores_resp.json()
    assert scores_data["host_id"] == str(host_id)
    assert scores_data["performance_score"] is not None
    assert scores_data["performance_breakdown"]["fp16_tflops_normalised"] is not None

    # 4. Get benchmark history (GET /v1/hosts/{id}/benchmarks/history)
    hist_resp = await rep_client.get(f"/v1/hosts/{host_id}/benchmarks/history")
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["host_id"] == str(host_id)
    assert hist_data["total_runs"] == 3


@pytest.mark.asyncio
async def test_v8_benchmark_envelope_fraud_flagging(db_session: AsyncSession, rep_client: AsyncClient):
    # Seed host and admin GPU envelope
    user_id = uuid.uuid4()
    user = User(id=user_id, email="spoof@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(
        id=host_id,
        user_id=user_id,
        status=HostStatus.VERIFIED,
        os_type="linux",
        agent_version="1.0.0",
    )
    db_session.add(host)

    # Add GpuModelEnvelope with max_value = 100.0 TFLOPS
    from libs.db_models.reputation_pricing_models import GpuModelEnvelope
    env_row = GpuModelEnvelope(
        gpu_model="RTX 4090",
        benchmark_type="gpu_fp16_tflops",
        min_value=50.0,
        max_value=100.0,
        unit="TFLOPS",
    )
    db_session.add(env_row)
    await db_session.commit()

    # Post a spoofed result of 999.0 TFLOPS (exceeds max_value=100.0)
    run_resp = await rep_client.post(
        f"/v1/hosts/{host_id}/benchmarks/run",
        json={
            "gpu_model": "RTX 4090",
            "sub_tests": [
                {"benchmark_type": "gpu_fp16_tflops", "value": 999.0, "unit": "TFLOPS"},
            ]
        }
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()
    assert run_data["status"] == "flagged"
    assert len(run_data["flags"]) == 1
    assert run_data["flags"][0]["benchmark_type"] == "gpu_fp16_tflops"
    assert "exceeds" in run_data["flags"][0]["reason"]
