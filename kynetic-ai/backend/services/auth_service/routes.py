"""
Auth Service — FastAPI routes.

Endpoints (per the Phase 1 API surface in the implementation plan):
    POST   /auth/signup
    POST   /auth/login
    POST   /auth/refresh
    POST   /auth/logout
    GET    /auth/me
    POST   /auth/phone/send-otp
    POST   /auth/phone/verify-otp
"""

import json

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError as JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from services.auth_service.config import get_settings
from services.auth_service.repository import (
    AuditLogRepository,
    DeviceCodeRepository,
    EventRepository,
    PhoneOTPRepository,
    RefreshTokenRepository,
    UserRepository,
)
from services.auth_service.schemas import (
    CliVersionResponse,
    DeviceCodeRequest,
    DeviceCodeResponse,
    DeviceTokenRequest,
    DeviceVerifyRequest,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    SendOTPRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
    VerifyOTPRequest,
)
from services.auth_service.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_refresh_token,
    verify_otp,
    verify_password,
)

logger = structlog.get_logger(__name__)
auth_router = APIRouter()
bearer_scheme = HTTPBearer(auto_error=False)
settings = get_settings()



# ---------------------------------------------------------------------------
# Helper: get current user from Bearer JWT
# ---------------------------------------------------------------------------
async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> str:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
        return payload["sub"]
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


# ---------------------------------------------------------------------------
# POST /auth/signup
# ---------------------------------------------------------------------------
@auth_router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """
    Register a new user account.

    Creates the user, issues an access + refresh token pair.
    Publishes a user.created event for downstream billing service initialization.
    """
    audit_repo = AuditLogRepository(session)
    user_repo = UserRepository(session, audit_repo)

    # Reject duplicate emails
    existing = await user_repo.get_by_email(body.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")

    user = await user_repo.create(
        email=body.email,
        plain_password=body.password,
        role=body.role,
        ip_address=ip,
        user_agent=ua,
    )

    access_token = create_access_token(user.id, user.role.value)
    raw_refresh, _ = generate_refresh_token()

    refresh_repo = RefreshTokenRepository(session, audit_repo)
    await refresh_repo.create(user.id, raw_refresh, user_agent=ua, ip_address=ip)

    await audit_repo.create(
        action="auth.signup",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"role": user.role.value, "ip": ip},
    )

    logger.info("user_signup", user_id=str(user.id), role=user.role.value)

    # Phase 3: Publish user.created event → billing_service initializes account
    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        await r.publish(
            "kynetic:events:user_created",
            json.dumps({
                "user_id": str(user.id),
                "email": user.email,
                "role": user.role.value,
            }),
        )
        await r.aclose()
    except Exception as exc:
        # Non-fatal — billing initialization is retryable via event replay
        logger.warning("user_created_event_publish_failed", error=str(exc))

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------
@auth_router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """Authenticate with email + password, receive token pair."""
    audit_repo = AuditLogRepository(session)
    user_repo = UserRepository(session, audit_repo)
    refresh_repo = RefreshTokenRepository(session, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")

    user = await user_repo.get_by_email(body.email)

    # Constant-time failure — always run verify even if user not found
    password_correct = verify_password(body.password, user.hashed_password) if user else False

    if not user or not password_correct or not user.is_active:
        await audit_repo.create(
            action="auth.login_failed",
            metadata={"email": body.email, "ip": ip},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    access_token = create_access_token(user.id, user.role.value)
    raw_refresh, _ = generate_refresh_token()
    await refresh_repo.create(user.id, raw_refresh, user_agent=ua, ip_address=ip)

    await audit_repo.create(
        action="auth.login",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"ip": ip},
    )

    logger.info("user_login", user_id=str(user.id))

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


# ---------------------------------------------------------------------------
# POST /auth/refresh
# ---------------------------------------------------------------------------
@auth_router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    body: RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.
    Implements refresh token rotation: the provided token is revoked,
    a new one is issued.
    """
    audit_repo = AuditLogRepository(session)
    refresh_repo = RefreshTokenRepository(session, audit_repo)
    user_repo = UserRepository(session, audit_repo)

    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")

    # Rotate: atomic single-use rotation with family reuse detection
    rotated = await refresh_repo.rotate(body.refresh_token, user_agent=ua, ip_address=ip)
    if not rotated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or reused refresh token.",
        )

    new_raw_refresh, new_token = rotated
    user = await user_repo.get_by_id(new_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
        )

    new_access = create_access_token(user.id, user.role.value)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_raw_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------
@auth_router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Revoke all refresh tokens for the current user."""
    import uuid as _uuid
    audit_repo = AuditLogRepository(session)
    refresh_repo = RefreshTokenRepository(session, audit_repo)

    user_id = _uuid.UUID(current_user_id)
    await refresh_repo.revoke_all_for_user(user_id)
    logger.info("user_logout", user_id=current_user_id)

    return MessageResponse(message="Logged out successfully.")


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------
@auth_router.get("/me", response_model=UserResponse)
async def get_me(
    current_user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    """Return the authenticated user's profile."""
    import uuid as _uuid
    audit_repo = AuditLogRepository(session)
    user_repo = UserRepository(session, audit_repo)

    user = await user_repo.get_by_id(_uuid.UUID(current_user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# POST /auth/phone/send-otp
# ---------------------------------------------------------------------------
@auth_router.post("/phone/send-otp", response_model=MessageResponse)
async def send_phone_otp(
    body: SendOTPRequest,
    current_user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """
    Generate and dispatch a 6-digit OTP to the provided phone number.

    Phase 1: OTP is generated and stored; SMS dispatch is stubbed
    (provider-agnostic interface — actual SMS wiring is a config concern).
    """
    import uuid as _uuid
    audit_repo = AuditLogRepository(session)
    otp_repo = PhoneOTPRepository(session)

    user_id = _uuid.UUID(current_user_id)
    _otp_record, raw_otp = await otp_repo.create(user_id, body.phone_number)

    await audit_repo.create(
        action="auth.phone_otp_sent",
        actor_id=user_id,
        resource_type="user",
        resource_id=str(user_id),
        metadata={"phone_number": body.phone_number},
    )

    # TODO Phase 1+: integrate SMS provider (Twilio / AWS SNS / Kaleyra for India)
    # For now, log the OTP in development only — NEVER in production
    import os
    if os.environ.get("ENVIRONMENT", "development") == "development":
        logger.debug("otp_generated_dev_only", otp=raw_otp, phone=body.phone_number)

    logger.info("phone_otp_sent", user_id=str(user_id), phone=body.phone_number)
    return MessageResponse(message="OTP sent to your phone number.")


# ---------------------------------------------------------------------------
# POST /auth/phone/verify-otp
# ---------------------------------------------------------------------------
@auth_router.post("/phone/verify-otp", response_model=MessageResponse)
async def verify_phone_otp(
    body: VerifyOTPRequest,
    current_user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Verify the OTP and mark the user's phone as verified."""
    import uuid as _uuid
    audit_repo = AuditLogRepository(session)
    otp_repo = PhoneOTPRepository(session)
    user_repo = UserRepository(session, audit_repo)

    user_id = _uuid.UUID(current_user_id)
    otp_record = await otp_repo.get_active(user_id, body.phone_number)

    if not otp_record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active OTP found for this phone number. Please request a new one.",
        )

    # Enforce attempt limit
    if otp_record.attempts >= settings.phone_otp_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Maximum OTP attempts exceeded. Please request a new OTP.",
        )

    await otp_repo.increment_attempts(otp_record)

    if not verify_otp(body.otp, otp_record.otp_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP.",
        )

    await otp_repo.mark_used(otp_record)
    await user_repo.mark_phone_verified(user_id, body.phone_number)

    logger.info("phone_verified", user_id=str(user_id), phone=body.phone_number)
    return MessageResponse(message="Phone number verified successfully.")


# ---------------------------------------------------------------------------
# Device Code Authorization Grant (RFC 8628)
# ---------------------------------------------------------------------------
@auth_router.post("/device/code", response_model=DeviceCodeResponse, tags=["Device Auth"])
async def create_device_code(
    body: DeviceCodeRequest | None = None,
    request: Request = None,
    session: AsyncSession = Depends(get_db_session),
) -> DeviceCodeResponse:
    """Initiates OAuth2 Device Authorization Grant for CLI login."""
    device_repo = DeviceCodeRepository(session)
    event_repo = EventRepository(session)

    ip = request.client.host if request and request.client else None
    ua = request.headers.get("User-Agent") if request else None

    record = await device_repo.create(user_agent=ua, ip_address=ip, expires_in_seconds=600)
    await event_repo.create(
        event_type="auth.device_code_requested",
        resource_type="device_code",
        resource_id=record.device_code,
        metadata={"user_code": record.user_code, "ip": ip},
    )

    host_base = str(request.base_url).rstrip("/") if request else "http://localhost:8000"
    verification_uri = f"{host_base}/auth/device/verify"
    verification_uri_complete = f"{verification_uri}?user_code={record.user_code}"

    return DeviceCodeResponse(
        device_code=record.device_code,
        user_code=record.user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_in=600,
        interval=5,
    )


@auth_router.post("/device/token", tags=["Device Auth"])
async def poll_device_token(
    body: DeviceTokenRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    """
    CLI polls this endpoint with device_code until the user approves in browser.
    Follows RFC 8628 error responses: authorization_pending, expired_token, access_denied.
    """
    from datetime import UTC, datetime
    from libs.db_models.user_models import DeviceCodeStatus

    audit_repo = AuditLogRepository(session)
    device_repo = DeviceCodeRepository(session)
    user_repo = UserRepository(session, audit_repo)
    refresh_repo = RefreshTokenRepository(session, audit_repo)

    record = await device_repo.get_by_device_code(body.device_code)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "invalid_grant", "error_description": "Invalid device code."},
        )

    now_time = datetime.now(UTC).replace(tzinfo=None) if record.expires_at.tzinfo is None else datetime.now(UTC)
    if record.expires_at < now_time or record.status == DeviceCodeStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "expired_token", "error_description": "The device code has expired. Please run 'kynetic login' again."},
        )

    if record.status == DeviceCodeStatus.DENIED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "access_denied", "error_description": "The end user denied the authorization request."},
        )

    if record.status == DeviceCodeStatus.PENDING or not record.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "authorization_pending", "error_description": "The authorization request is pending user approval."},
        )

    # Approved: issue token pair
    user = await user_repo.get_by_id(record.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_grant", "error_description": "User account is inactive or not found."},
        )

    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")

    access_token = create_access_token(user.id, user.role.value)
    raw_refresh, _ = generate_refresh_token()
    await refresh_repo.create(user.id, raw_refresh, user_agent=ua, ip_address=ip)

    event_repo = EventRepository(session)
    await event_repo.create(
        event_type="auth.device_login_success",
        actor_id=user.id,
        resource_type="device_code",
        resource_id=record.device_code,
        metadata={"ip": ip, "user_agent": ua},
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserResponse.model_validate(user),
    )


@auth_router.post("/device/verify", response_model=MessageResponse, tags=["Device Auth"])
async def verify_device_code(
    body: DeviceVerifyRequest,
    current_user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """User authorizes a device code using the user_code displayed on the CLI."""
    import uuid as _uuid
    from datetime import UTC, datetime
    from libs.db_models.user_models import DeviceCodeStatus

    device_repo = DeviceCodeRepository(session)
    event_repo = EventRepository(session)

    user_id = _uuid.UUID(current_user_id)
    record = await device_repo.get_by_user_code(body.user_code)

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid user code. Please check the code shown in your terminal.",
        )

    now_time = datetime.now(UTC).replace(tzinfo=None) if record.expires_at.tzinfo is None else datetime.now(UTC)
    if record.expires_at < now_time or record.status == DeviceCodeStatus.EXPIRED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This user code has expired. Please run 'kynetic login' again on your device.",
        )

    if record.status == DeviceCodeStatus.APPROVED:
        return MessageResponse(message="Device has already been authorized.")

    await device_repo.approve(record, user_id)
    await event_repo.create(
        event_type="auth.device_code_approved",
        actor_id=user_id,
        resource_type="device_code",
        resource_id=record.device_code,
        metadata={"user_code": record.user_code},
    )

    logger.info("device_code_approved", user_id=current_user_id, user_code=body.user_code)
    return MessageResponse(message="Device authorized successfully! You may return to your terminal.")


@auth_router.get("/cli/version", response_model=CliVersionResponse, tags=["CLI"])
async def get_cli_version() -> CliVersionResponse:
    """Returns the latest CLI version information."""
    return CliVersionResponse(
        version="1.0.0",
        min_supported_version="1.0.0",
        download_url="https://github.com/kynetic-ai/kynetic/releases/latest",
        release_notes="Kynetic CLI v1.0.0 Phase A Initial Release",
    )


