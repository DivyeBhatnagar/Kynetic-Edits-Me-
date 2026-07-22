"""
Security Service — FastAPI Routes.

Admin routes (require admin JWT):
  POST   /admin/kill-switch
  GET    /admin/security-events

Developer routes (require user JWT):
  GET    /users/{user_id}/trust-tier
  POST   /identity/verify/id-document
  POST   /security/fingerprint

Internal routes (no auth — called service-to-service):
  POST   /internal/scan-image
"""

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common.database import get_async_session
from libs.db_models.security_models import (
    KillSwitchTargetType,
    SecurityEventSeverity,
    SecurityEventType,
    TrustTierLevel,
)
from services.security_service import kill_switch as ks_module
from services.security_service.config import get_settings
from services.security_service.image_scanner import scan_image
from services.security_service.repository import (
    DeviceFingerprintRepository,
    KillSwitchRepository,
    SecurityEventRepository,
    TrustTierRepository,
)
from services.security_service.schemas import (
    FingerprintCheckResponse,
    FingerprintRequest,
    IDVerificationRequest,
    IDVerificationResponse,
    ImageScanResult,
    KillSwitchRequest,
    KillSwitchResponse,
    SecurityEventListResponse,
    SecurityEventResponse,
    TrustTierResponse,
    TrustTierUpdateRequest,
)
from services.security_service.trust_tier import get_tier_defaults

log = structlog.get_logger(__name__)
settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)
router = APIRouter(prefix="/v1")


# ── Auth helpers ───────────────────────────────────────────────────────────

import jwt as pyjwt


def _decode_jwt(token: str, secret: str) -> dict[str, Any]:
    try:
        return pyjwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def get_current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> uuid.UUID:
    if not creds:
        raise HTTPException(status_code=401, detail="Authentication required")
    payload = _decode_jwt(creds.credentials, settings.jwt_secret_key)
    return uuid.UUID(payload["sub"])


def get_admin_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> uuid.UUID:
    """Admin endpoints require a token signed with the separate admin secret."""
    if not creds:
        raise HTTPException(status_code=401, detail="Admin authentication required")
    payload = _decode_jwt(creds.credentials, settings.admin_jwt_secret_key)
    if not payload.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return uuid.UUID(payload["sub"])


# ── Admin — Kill Switch ────────────────────────────────────────────────────

@router.post("/admin/kill-switch", response_model=KillSwitchResponse, tags=["Admin"])
async def trigger_kill_switch(
    body: KillSwitchRequest,
    admin_id: uuid.UUID = Depends(get_admin_user_id),
    session: AsyncSession = Depends(get_async_session),
    request: Request = None,
):
    """
    Instantly suspends an instance, host, or account.
    Requires admin JWT. Every invocation is permanently recorded.
    """
    log.warning(
        "kill_switch.triggered",
        admin_id=str(admin_id),
        target_type=body.target_type.value,
        target_id=body.target_id,
    )

    # Perform the suspension
    # Extract the raw bearer token to forward to downstream services
    raw_token = request.headers.get("Authorization", "").replace("Bearer ", "") if request else ""

    if body.target_type == KillSwitchTargetType.instance:
        broadcast_result = await ks_module.suspend_instance(body.target_id, raw_token)
    elif body.target_type == KillSwitchTargetType.host:
        broadcast_result = await ks_module.suspend_host(body.target_id, raw_token)
    elif body.target_type == KillSwitchTargetType.account:
        target_user_id = uuid.UUID(body.target_id)
        broadcast_result = await ks_module.suspend_account(target_user_id, raw_token)
        # Freeze wallet in TrustTier
        trust_repo = TrustTierRepository(session)
        await trust_repo.freeze_wallet(target_user_id)
    else:
        raise HTTPException(status_code=400, detail="Unknown target_type")

    # Write immutable audit records
    ks_repo = KillSwitchRepository(session)
    ev = await ks_repo.create(
        target_type=body.target_type,
        target_id=body.target_id,
        triggered_by=admin_id,
        reason=body.reason,
        broadcast_result=broadcast_result,
    )

    sec_repo = SecurityEventRepository(session)
    await sec_repo.log(
        SecurityEventType.kill_switch_triggered,
        SecurityEventSeverity.critical,
        resource_type=body.target_type.value,
        resource_id=body.target_id,
        user_id=admin_id,
        details={"reason": body.reason, "broadcast_result": broadcast_result},
    )

    await session.commit()
    return KillSwitchResponse(
        id=ev.id,
        target_type=ev.target_type,
        target_id=ev.target_id,
        triggered_by=ev.triggered_by,
        reason=ev.reason,
        triggered_at=ev.triggered_at,
        broadcast_result=ev.broadcast_result,
    )


# ── Admin — Security Events ────────────────────────────────────────────────

@router.get("/admin/security-events", response_model=SecurityEventListResponse, tags=["Admin"])
async def list_security_events(
    admin_id: uuid.UUID = Depends(get_admin_user_id),
    severity: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
):
    repo = SecurityEventRepository(session)
    sev = SecurityEventSeverity(severity) if severity else None
    et = SecurityEventType(event_type) if event_type else None
    items, total = await repo.list(
        severity=sev, event_type=et, user_id=user_id, page=page, page_size=page_size
    )
    return SecurityEventListResponse(
        items=[SecurityEventResponse.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── Trust Tier ─────────────────────────────────────────────────────────────

@router.get("/users/{user_id}/trust-tier", response_model=TrustTierResponse, tags=["Trust"])
async def get_user_trust_tier(
    user_id: uuid.UUID,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    # Users can only view their own tier; admins can view any
    if current_user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    repo = TrustTierRepository(session)
    tier = await repo.get_or_create_default(user_id)
    return TrustTierResponse.model_validate(tier)


@router.put("/admin/users/{user_id}/trust-tier", response_model=TrustTierResponse, tags=["Admin"])
async def update_user_trust_tier(
    user_id: uuid.UUID,
    body: TrustTierUpdateRequest,
    admin_id: uuid.UUID = Depends(get_admin_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    repo = TrustTierRepository(session)
    tier = await repo.update(
        user_id,
        tier=body.tier,
        max_instance_vcpus=body.max_instance_vcpus,
        max_gpu_vram_gb=body.max_gpu_vram_gb,
        max_gpu_hours_month=body.max_gpu_hours_month,
        max_spend_usd_month=body.max_spend_usd_month,
        is_wallet_frozen=body.is_wallet_frozen,
    )

    # Log tier change
    sec_repo = SecurityEventRepository(session)
    await sec_repo.log(
        SecurityEventType.trust_tier_change,
        SecurityEventSeverity.info,
        resource_type="user",
        resource_id=str(user_id),
        user_id=admin_id,
        details={"new_tier": body.tier.value, "reason": body.reason},
    )

    await session.commit()
    return TrustTierResponse.model_validate(tier)


# ── Identity Verification ──────────────────────────────────────────────────

@router.post("/identity/verify/id-document", response_model=IDVerificationResponse, tags=["Identity"])
async def submit_id_document(
    body: IDVerificationRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_async_session),
):
    """
    Phase 5 stub: records the ID verification claim and sets the user's tier
    to pending_review. In production, this triggers manual review or a
    third-party OCR + liveness check workflow.
    """
    sec_repo = SecurityEventRepository(session)
    await sec_repo.log(
        SecurityEventType.trust_tier_change,
        SecurityEventSeverity.info,
        resource_type="user",
        resource_id=str(current_user_id),
        user_id=current_user_id,
        details={
            "action": "id_document_submitted",
            "document_type": body.document_type,
            "claim": body.claim_document_uploaded,
        },
    )
    await session.commit()

    return IDVerificationResponse(
        user_id=current_user_id,
        status="pending_review",
        message="Your ID document has been submitted for review. "
                "Trust tier will be upgraded to tier2 once verified (typically 24–48 hours).",
    )


# ── Device Fingerprint ─────────────────────────────────────────────────────

@router.post("/security/fingerprint", response_model=FingerprintCheckResponse, tags=["Security"])
async def record_device_fingerprint(
    body: FingerprintRequest,
    current_user_id: uuid.UUID = Depends(get_current_user_id),
    request: Request = None,
    session: AsyncSession = Depends(get_async_session),
):
    """
    Records the device fingerprint for the authenticated user.
    Called automatically by the frontend at login/signup.
    """
    ip = request.client.host if request and request.client else body.ip_address
    fp_repo = DeviceFingerprintRepository(session)
    _, is_new = await fp_repo.upsert(
        current_user_id,
        body.fingerprint_hash,
        ip_address=ip,
        user_agent=body.user_agent,
    )

    matching_users = await fp_repo.count_users_with_fingerprint(body.fingerprint_hash)
    multi_account = matching_users > 1

    if multi_account:
        sec_repo = SecurityEventRepository(session)
        await sec_repo.log(
            SecurityEventType.multi_account_suspected,
            SecurityEventSeverity.warning,
            resource_type="user",
            resource_id=str(current_user_id),
            user_id=current_user_id,
            ip_address=ip,
            details={
                "fingerprint_hash": body.fingerprint_hash,
                "matching_user_count": matching_users,
            },
        )

    await session.commit()
    return FingerprintCheckResponse(
        fingerprint_hash=body.fingerprint_hash,
        is_new_device=is_new,
        multi_account_suspected=multi_account,
        matching_user_count=matching_users,
    )


# ── Internal — Image Scan ──────────────────────────────────────────────────

@router.post("/internal/scan-image", response_model=ImageScanResult, tags=["Internal"])
async def scan_image_endpoint(
    image: str = Query(..., description="Full image reference, e.g. docker.io/library/ubuntu:24.04"),
    instance_id: str | None = Query(default=None),
):
    """
    Internal endpoint — called by provisioning_service before starting a container.
    No auth required (internal network only — not exposed through the gateway).
    """
    result = scan_image(image)
    log.info(
        "security.scan_image",
        image=image,
        instance_id=instance_id,
        blocked=result.blocked,
        findings=result.finding_count,
    )
    return result
