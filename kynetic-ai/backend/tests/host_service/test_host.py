"""
Host Service — Integration Tests (Phase 2 exit criteria).

Tests every endpoint and the core lifecycle:
  POST /hosts/register          — happy path, spec mismatch flagging
  POST /hosts/heartbeat         — accepted for valid host
  POST /hosts/{id}/benchmarks   — full suite → VERIFIED transition
  GET  /hosts/{id}              — returns host + latest spec
  GET  /hosts/{id}/benchmarks   — returns stored benchmark records
  POST /hosts/{id}/benchmarks/rerun — 202 Accepted

Hardware verification tests:
  - RTX 4090 with correct VRAM → passes
  - RTX 4090 with spoofed VRAM → flagged
  - CPU-only machine (no GPU) → passes
  - Unknown GPU model → warning only (not flagged)
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from services.host_service.main import app as host_app
from libs.db_models.database import get_db_session


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
async def host_client(db_session) -> AsyncClient:
    """AsyncClient pointing at the host service app with test DB."""
    from tests.conftest import _override_get_db_session
    host_app.dependency_overrides[get_db_session] = _override_get_db_session
    async with AsyncClient(
        transport=ASGITransport(app=host_app),
        base_url="http://test",
    ) as client:
        yield client
    host_app.dependency_overrides.clear()


async def _make_user_token(auth_client: AsyncClient, email: str = "host@example.com") -> tuple[str, str]:
    """Create a user via auth service and return (user_id, access_token)."""
    resp = await auth_client.post("/auth/signup", json={
        "email": email,
        "password": "HostPass99",
        "role": "host",
    })
    assert resp.status_code == 201
    data = resp.json()
    return data["user"]["id"], data["access_token"]


# ── Helpers ────────────────────────────────────────────────────────────────

VALID_HARDWARE_RTX4090 = {
    "cpu_model": "Intel Core i9-13900K",
    "cpu_cores": 24,
    "cpu_threads": 32,
    "ram_gb": 64.0,
    "disk_type": "nvme",
    "disk_gb": 2000.0,
    "gpu_model": "NVIDIA GeForce RTX 4090",
    "gpu_count": 1,
    "gpu_vram_gb": 24.0,
    "driver_version": "535.104.05",
    "cuda_version": "12.1",
}

VALID_HARDWARE_CPU_ONLY = {
    "cpu_model": "AMD EPYC 7763",
    "cpu_cores": 64,
    "cpu_threads": 128,
    "ram_gb": 256.0,
    "disk_type": "nvme",
    "disk_gb": 4000.0,
    "gpu_model": None,
    "gpu_count": 0,
    "gpu_vram_gb": None,
    "driver_version": None,
    "cuda_version": None,
}

SPOOFED_HARDWARE = {
    **VALID_HARDWARE_RTX4090,
    "gpu_vram_gb": 80.0,   # RTX 4090 only has 24 GB — 80 GB is an A100 VRAM figure
}

VALID_BENCHMARKS = [
    {"benchmark_type": "llm_inference", "score": 4200.5, "raw_metrics": {"tokens_per_sec": 4200.5}},
    {"benchmark_type": "image_gen", "score": 12.3, "raw_metrics": {"steps_per_sec": 12.3}},
    {"benchmark_type": "flops", "score": 82.4, "raw_metrics": {"tflops": 82.4}},
]


async def _register_host(
    host_client: AsyncClient,
    auth_token: str,
    hardware: dict = None,
    agent_id: str = None,
) -> dict:
    resp = await host_client.post(
        "/hosts/register",
        json={
            "agent_id": agent_id or str(uuid.uuid4()),
            "agent_version": "0.1.0",
            "os_type": "linux",
            "hardware": hardware or VALID_HARDWARE_RTX4090,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    return resp


# ── Health check ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_host_service_healthz(host_client: AsyncClient):
    resp = await host_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["service"] == "host_service"


# ── POST /hosts/register ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_gpu_host_success(auth_client: AsyncClient, host_client: AsyncClient):
    _, token = await _make_user_token(auth_client)

    resp = await _register_host(host_client, token)
    assert resp.status_code == 201

    data = resp.json()
    assert "host_id" in data
    assert data["status"] == "benchmarking"     # Spec passed → moved to BENCHMARKING
    assert "mtls_client_cert_pem" in data
    assert "BEGIN CERTIFICATE" in data["mtls_client_cert_pem"]


@pytest.mark.asyncio
async def test_register_cpu_only_host(auth_client: AsyncClient, host_client: AsyncClient):
    _, token = await _make_user_token(auth_client, email="cpuhost@example.com")

    resp = await _register_host(host_client, token, hardware=VALID_HARDWARE_CPU_ONLY)
    assert resp.status_code == 201

    data = resp.json()
    # CPU-only passes spec check (no GPU to cross-check)
    assert data["status"] == "benchmarking"


@pytest.mark.asyncio
async def test_register_spoofed_vram_is_flagged(auth_client: AsyncClient, host_client: AsyncClient):
    _, token = await _make_user_token(auth_client, email="spoof@example.com")

    resp = await _register_host(host_client, token, hardware=SPOOFED_HARDWARE)
    assert resp.status_code == 201   # Registration always returns 201

    data = resp.json()
    # Spoofed VRAM → FLAGGED status
    assert data["status"] == "flagged"
    assert "mismatch" in data["message"].lower() or "flagged" in data["message"].lower()


@pytest.mark.asyncio
async def test_register_requires_auth(host_client: AsyncClient):
    resp = await host_client.post(
        "/hosts/register",
        json={
            "agent_id": str(uuid.uuid4()),
            "agent_version": "0.1.0",
            "os_type": "linux",
            "hardware": VALID_HARDWARE_RTX4090,
        },
    )
    assert resp.status_code == 401


# ── POST /hosts/heartbeat ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_accepted(auth_client: AsyncClient, host_client: AsyncClient):
    _, token = await _make_user_token(auth_client, email="hbhost@example.com")
    reg = await _register_host(host_client, token)
    host_id = reg.json()["host_id"]

    # Heartbeat doesn't require auth (mTLS in prod) — just host_id
    with patch("services.host_service.routes.process_heartbeat") as mock_task:
        mock_task.delay = MagicMock()
        resp = await host_client.post("/hosts/heartbeat", json={
            "host_id": host_id,
            "status": "idle",
            "temperature_c": 62.5,
            "power_draw_w": 180.0,
            "gpu_utilization_pct": 0.0,
            "ram_used_gb": 12.3,
        })
    assert resp.status_code == 200
    assert "host_status" in resp.json()


@pytest.mark.asyncio
async def test_heartbeat_unknown_host(host_client: AsyncClient):
    resp = await host_client.post("/hosts/heartbeat", json={
        "host_id": str(uuid.uuid4()),
        "status": "idle",
    })
    assert resp.status_code == 404


# ── POST /hosts/{id}/benchmarks — full suite submission ───────────────────

@pytest.mark.asyncio
async def test_benchmark_submission_transitions_to_verified(
    auth_client: AsyncClient, host_client: AsyncClient
):
    _, token = await _make_user_token(auth_client, email="bench@example.com")
    reg = await _register_host(host_client, token)
    host_id = reg.json()["host_id"]

    resp = await host_client.post(
        f"/hosts/{host_id}/benchmarks",
        json={"host_id": host_id, "results": VALID_BENCHMARKS},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200

    data = resp.json()
    assert data["all_passed"] is True
    assert data["host_status"] == "verified"


@pytest.mark.asyncio
async def test_partial_benchmarks_stays_benchmarking(
    auth_client: AsyncClient, host_client: AsyncClient
):
    """Only 2 of 3 benchmark types submitted — should NOT transition to verified."""
    _, token = await _make_user_token(auth_client, email="partial@example.com")
    reg = await _register_host(host_client, token)
    host_id = reg.json()["host_id"]

    partial = VALID_BENCHMARKS[:2]  # Only LLM + image_gen, no flops
    resp = await host_client.post(
        f"/hosts/{host_id}/benchmarks",
        json={"host_id": host_id, "results": partial},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["host_status"] != "verified"


@pytest.mark.asyncio
async def test_benchmark_submission_wrong_user(
    auth_client: AsyncClient, host_client: AsyncClient
):
    """User B cannot submit benchmarks for User A's host."""
    _, token_a = await _make_user_token(auth_client, email="userA@example.com")
    _, token_b = await _make_user_token(auth_client, email="userB@example.com")

    reg = await _register_host(host_client, token_a)
    host_id = reg.json()["host_id"]

    resp = await host_client.post(
        f"/hosts/{host_id}/benchmarks",
        json={"host_id": host_id, "results": VALID_BENCHMARKS},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 403


# ── GET /hosts/{id} ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_host_returns_details_with_spec(
    auth_client: AsyncClient, host_client: AsyncClient
):
    _, token = await _make_user_token(auth_client, email="gethost@example.com")
    reg = await _register_host(host_client, token)
    host_id = reg.json()["host_id"]

    resp = await host_client.get(
        f"/hosts/{host_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == host_id
    assert data["os_type"] == "linux"
    assert data["latest_spec"] is not None
    assert data["latest_spec"]["cpu_cores"] == 24
    assert data["latest_spec"]["gpu_model"] == "NVIDIA GeForce RTX 4090"


@pytest.mark.asyncio
async def test_get_host_not_found(host_client: AsyncClient, auth_client: AsyncClient):
    _, token = await _make_user_token(auth_client, email="ghost2@example.com")
    resp = await host_client.get(
        f"/hosts/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


# ── GET /hosts/{id}/benchmarks ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_benchmarks_returns_all_results(
    auth_client: AsyncClient, host_client: AsyncClient
):
    _, token = await _make_user_token(auth_client, email="allbench@example.com")
    reg = await _register_host(host_client, token)
    host_id = reg.json()["host_id"]

    # Submit benchmarks
    await host_client.post(
        f"/hosts/{host_id}/benchmarks",
        json={"host_id": host_id, "results": VALID_BENCHMARKS},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await host_client.get(
        f"/hosts/{host_id}/benchmarks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 3
    types = {r["benchmark_type"] for r in results}
    assert types == {"llm_inference", "image_gen", "flops"}


# ── POST /hosts/{id}/benchmarks/rerun ────────────────────────────────────

@pytest.mark.asyncio
async def test_rerun_benchmarks_accepted(
    auth_client: AsyncClient, host_client: AsyncClient
):
    _, token = await _make_user_token(auth_client, email="rerun@example.com")
    reg = await _register_host(host_client, token)
    host_id = reg.json()["host_id"]

    with patch("services.host_service.routes.trigger_rebenchmark") as mock_task:
        mock_task.delay = MagicMock()
        resp = await host_client.post(
            f"/hosts/{host_id}/benchmarks/rerun",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 202
    assert "signal sent" in resp.json()["message"].lower()


# ── Hardware Verification Unit Tests ─────────────────────────────────────

@pytest.mark.asyncio
async def test_verification_rtx4090_correct_vram():
    from services.host_service.verification import verify_hardware_spec
    from services.host_service.schemas import HardwareSpecSchema

    spec = HardwareSpecSchema(**VALID_HARDWARE_RTX4090)
    result = verify_hardware_spec(spec, vram_tolerance_pct=10.0)
    assert result.passed is True
    assert result.flags == []


@pytest.mark.asyncio
async def test_verification_rtx4090_spoofed_vram():
    from services.host_service.verification import verify_hardware_spec
    from services.host_service.schemas import HardwareSpecSchema

    spec = HardwareSpecSchema(**SPOOFED_HARDWARE)
    result = verify_hardware_spec(spec, vram_tolerance_pct=10.0)
    assert result.passed is False
    assert any("VRAM mismatch" in f or "mismatch" in f.lower() for f in result.flags)


@pytest.mark.asyncio
async def test_verification_cpu_only_passes():
    from services.host_service.verification import verify_hardware_spec
    from services.host_service.schemas import HardwareSpecSchema

    spec = HardwareSpecSchema(**VALID_HARDWARE_CPU_ONLY)
    result = verify_hardware_spec(spec)
    assert result.passed is True


@pytest.mark.asyncio
async def test_verification_unknown_gpu_warns_not_flags():
    from services.host_service.verification import verify_hardware_spec
    from services.host_service.schemas import HardwareSpecSchema

    spec = HardwareSpecSchema(**{
        **VALID_HARDWARE_RTX4090,
        "gpu_model": "FutureTech Quantum X1",
        "gpu_vram_gb": 48.0,
    })
    result = verify_hardware_spec(spec)
    # Unknown GPU = warning, NOT a flag
    assert result.passed is True
    assert len(result.warnings) > 0
    assert "not in known signatures" in result.warnings[0]


@pytest.mark.asyncio
async def test_verification_implausible_ram_flagged():
    from services.host_service.verification import verify_hardware_spec
    from services.host_service.schemas import HardwareSpecSchema

    spec = HardwareSpecSchema(**{**VALID_HARDWARE_CPU_ONLY, "ram_gb": 0.1})
    result = verify_hardware_spec(spec)
    assert result.passed is False
    assert any("RAM" in f for f in result.flags)
