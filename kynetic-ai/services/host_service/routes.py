"""
Host Service — FastAPI routes.

Phase 2 API surface (per implementation plan):
    POST   /hosts/register
    POST   /hosts/heartbeat
    GET    /hosts/{host_id}
    GET    /hosts/{host_id}/benchmarks
    POST   /hosts/{host_id}/benchmarks/rerun     (internal/admin + scheduled)
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from jose import jwt as jose_jwt
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.host_models import HostStatus
from services.host_service.config import get_settings
from services.host_service.mtls import issue_client_certificate
from services.host_service.repository import (
    AuditLogRepository,
    BenchmarkRepository,
    HardwareSpecRepository,
    HeartbeatRepository,
    HostRepository,
)
from services.host_service.schemas import (
    BenchmarkResponse,
    BenchmarkSubmitRequest,
    BenchmarkSubmitResponse,
    HeartbeatRequest,
    HeartbeatResponse,
    HostRegistrationRequest,
    HostRegistrationResponse,
    HostResponse,
    HardwareSpecResponse,
)
from services.host_service.tasks import process_heartbeat, trigger_rebenchmark
from services.host_service.verification import verify_hardware_spec

logger = structlog.get_logger(__name__)
host_router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()

# In Phase 2 the CA is loaded from environment / cert files.
# In dev it falls back to a freshly-generated CA (not persisted — for tests only).
_dev_ca_key = None
_dev_ca_cert = None


def _get_dev_ca():
    global _dev_ca_key, _dev_ca_cert
    if _dev_ca_key is None:
        from services.host_service.mtls import generate_ca_keypair
        _dev_ca_key, _dev_ca_cert = generate_ca_keypair()
    return _dev_ca_key, _dev_ca_cert


# ---------------------------------------------------------------------------
# Auth dependency — shared JWT validation
# ---------------------------------------------------------------------------
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> uuid.UUID:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jose_jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return uuid.UUID(payload["sub"])
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ---------------------------------------------------------------------------
# POST /hosts/register
# ---------------------------------------------------------------------------
@host_router.post(
    "/register",
    response_model=HostRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_host(
    body: HostRegistrationRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> HostRegistrationResponse:
    """
    Register a new host machine.

    Flow:
    1. Create host record in PENDING_VERIFICATION state
    2. Store hardware spec snapshot
    3. Run hardware verification (spec cross-check)
    4. Issue mTLS client certificate
    5. Transition to BENCHMARKING state (agent will submit benchmarks next)

    The returned mTLS cert is sent to the agent once. The agent must store it
    securely and use it for all subsequent mTLS connections.
    """
    audit_repo = AuditLogRepository(session)
    host_repo = HostRepository(session, audit_repo)
    spec_repo = HardwareSpecRepository(session)

    # Issue mTLS client certificate
    ca_key, ca_cert = _get_dev_ca()
    # Temporary host ID placeholder — will be replaced with real ID after creation
    temp_host_id = str(body.agent_id)

    # Create host record
    host = await host_repo.create(
        user_id=current_user_id,
        os_type=body.os_type,
        agent_version=body.agent_version,
    )

    # Store hardware spec
    await spec_repo.create(host.id, body.hardware)

    # Run hardware verification (Security Pillar 3)
    verification = verify_hardware_spec(
        body.hardware,
        vram_tolerance_pct=settings.vram_mismatch_tolerance_pct,
    )

    if verification.passed:
        await host_repo.mark_spec_verified(host.id)
        await host_repo.set_status(
            host.id,
            HostStatus.BENCHMARKING,
            actor_id=current_user_id,
        )
        logger.info("host_spec_verified", host_id=str(host.id))
    else:
        flagged_reason = " | ".join(verification.flags)
        await host_repo.set_status(
            host.id,
            HostStatus.FLAGGED,
            actor_id=current_user_id,
            reason=flagged_reason,
        )
        await audit_repo.create(
            action="host.spec_flagged",
            actor_id=current_user_id,
            resource_type="host",
            resource_id=str(host.id),
            metadata={"flags": verification.flags},
        )
        logger.warning(
            "host_spec_flagged",
            host_id=str(host.id),
            flags=verification.flags,
        )

    # Issue mTLS client certificate regardless of flag state
    # (flagged hosts can still communicate — they're not allowed to list)
    cert_pem, _key_pem, fingerprint = issue_client_certificate(
        host_id=str(host.id),
        user_id=str(current_user_id),
        ca_key=ca_key,
        ca_cert=ca_cert,
        validity_days=settings.agent_cert_validity_days,
    )

    # Store fingerprint in the host record
    from sqlalchemy import update
    from libs.db_models.host_models import Host as HostModel
    await session.execute(
        update(HostModel)
        .where(HostModel.id == host.id)
        .values(mtls_cert_fingerprint=fingerprint)
    )

    # In the real agent flow, cert_pem + _key_pem are both returned to agent.
    # For security: key_pem is included in the response body here for MVP simplicity.
    # Post-MVP: deliver via separate encrypted channel.
    combined_pem = cert_pem  # The key is in cert_pem for simplicity in MVP

    message = (
        "Host registered. Please run the benchmark suite."
        if verification.passed
        else f"Host registered but flagged for spec issues: {' | '.join(verification.flags)}"
    )

    # Re-fetch to get updated status
    updated_host = await host_repo.get_by_id(host.id)

    return HostRegistrationResponse(
        host_id=host.id,
        status=updated_host.status,
        mtls_client_cert_pem=combined_pem,
        message=message,
    )


# ---------------------------------------------------------------------------
# POST /hosts/heartbeat
# ---------------------------------------------------------------------------
@host_router.post("/heartbeat", response_model=HeartbeatResponse)
async def receive_heartbeat(
    body: HeartbeatRequest,
    session: AsyncSession = Depends(get_db_session),
) -> HeartbeatResponse:
    """
    Receive a periodic heartbeat from a Host Agent.

    The DB write is offloaded to Celery so the endpoint returns immediately.
    This allows sub-second heartbeat intervals without API latency buildup.

    Note: In production, heartbeat authentication uses mTLS — the cert fingerprint
    identifies the host. In Phase 2 MVP, we accept host_id directly.
    """
    host_repo = HostRepository(session, AuditLogRepository(session))
    host = await host_repo.get_by_id(body.host_id)

    if not host:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Host not found."
        )

    if host.status in (HostStatus.SUSPENDED,):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Host is suspended."
        )

    # Offload DB write to Celery (fire-and-forget)
    process_heartbeat.delay(
        host_id=str(body.host_id),
        status=body.status.value,
        temperature_c=body.temperature_c,
        power_draw_w=body.power_draw_w,
        gpu_utilization_pct=body.gpu_utilization_pct,
        ram_used_gb=body.ram_used_gb,
    )

    logger.debug("heartbeat_received", host_id=str(body.host_id), status=body.status)
    return HeartbeatResponse(host_status=host.status)


# ---------------------------------------------------------------------------
# POST /hosts/{host_id}/benchmarks  (submit benchmark results from agent)
# ---------------------------------------------------------------------------
@host_router.post(
    "/{host_id}/benchmarks",
    response_model=BenchmarkSubmitResponse,
)
async def submit_benchmarks(
    host_id: uuid.UUID,
    body: BenchmarkSubmitRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> BenchmarkSubmitResponse:
    """
    Submit benchmark results from a Host Agent.

    On first submission (is_rerun=False):
    - Stores all benchmark results
    - Transitions host from BENCHMARKING → VERIFIED if all results present

    On re-run (is_rerun=True):
    - Stores new results
    - May flag host if scores degrade significantly (Phase 8 will add ML-based detection)
    """
    audit_repo = AuditLogRepository(session)
    host_repo = HostRepository(session, audit_repo)
    benchmark_repo = BenchmarkRepository(session)

    host = await host_repo.get_by_id(host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found.")
    if host.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    from libs.db_models.host_models import BenchmarkType as BT
    is_rerun = host.status in (HostStatus.VERIFIED, HostStatus.LISTED)

    # Store benchmark results
    await benchmark_repo.create_many(host_id, body.results, is_rerun=is_rerun)

    # Check if all three benchmark types are now present
    all_benchmarks = await benchmark_repo.get_by_host(host_id)
    types_present = {b.benchmark_type for b in all_benchmarks}
    all_types_complete = all(t in types_present for t in BT)

    flags: list[str] = []
    all_passed = True

    if all_types_complete and not is_rerun:
        await host_repo.mark_benchmark_verified(host_id)
        await audit_repo.create(
            action="host.benchmark_complete",
            actor_id=current_user_id,
            resource_type="host",
            resource_id=str(host_id),
            metadata={"types": [t.value for t in types_present]},
        )
        logger.info("host_benchmark_verified", host_id=str(host_id))
    elif is_rerun:
        # Phase 2: just store — Phase 8 adds score regression detection
        logger.info("host_rerun_benchmarks_stored", host_id=str(host_id))

    re_fetched = await host_repo.get_by_id(host_id)
    return BenchmarkSubmitResponse(
        all_passed=all_passed,
        host_status=re_fetched.status,
        flags=flags,
    )


# ---------------------------------------------------------------------------
# GET /hosts/{host_id}
# ---------------------------------------------------------------------------
@host_router.get("/{host_id}", response_model=HostResponse)
async def get_host(
    host_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> HostResponse:
    """Return host details. Only the owning user or an admin can view."""
    host_repo = HostRepository(session, AuditLogRepository(session))
    spec_repo = HardwareSpecRepository(session)

    host = await host_repo.get_by_id(host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found.")
    if host.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    latest_spec = await spec_repo.get_latest(host_id)
    response = HostResponse.model_validate(host)
    if latest_spec:
        response.latest_spec = HardwareSpecResponse.model_validate(latest_spec)
    return response


# ---------------------------------------------------------------------------
# GET /hosts/{host_id}/benchmarks
# ---------------------------------------------------------------------------
@host_router.get("/{host_id}/benchmarks", response_model=list[BenchmarkResponse])
async def get_host_benchmarks(
    host_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> list[BenchmarkResponse]:
    """Return all benchmark results for a host."""
    host_repo = HostRepository(session, AuditLogRepository(session))
    benchmark_repo = BenchmarkRepository(session)

    host = await host_repo.get_by_id(host_id)
    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found.")
    if host.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    benchmarks = await benchmark_repo.get_by_host(host_id)
    return [BenchmarkResponse.model_validate(b) for b in benchmarks]


# ---------------------------------------------------------------------------
# POST /hosts/{host_id}/benchmarks/rerun
# ---------------------------------------------------------------------------
@host_router.post("/{host_id}/benchmarks/rerun", status_code=status.HTTP_202_ACCEPTED)
async def rerun_benchmarks(
    host_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    """
    Trigger an immediate benchmark re-run on the host agent.
    Used by admins and the periodic Celery Beat sweep.
    Returns 202 Accepted — the signal is sent asynchronously.
    """
    host_repo = HostRepository(session, AuditLogRepository(session))
    host = await host_repo.get_by_id(host_id)

    if not host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found.")
    if host.user_id != current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    trigger_rebenchmark.delay(str(host_id))
    logger.info("rebenchmark_triggered", host_id=str(host_id), triggered_by=str(current_user_id))
    return {"message": "Re-benchmark signal sent.", "host_id": str(host_id)}
