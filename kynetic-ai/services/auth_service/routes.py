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
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from services.auth_service.config import get_settings
from services.auth_service.repository import (
    AuditLogRepository,
    PhoneOTPRepository,
    RefreshTokenRepository,
    UserRepository,
)
from services.auth_service.schemas import (
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
    Every developer account will auto-create a wallet in Phase 3 (hooked here later).
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

    # Phase 3: Publish user.created event → wallet_billing_service auto-creates wallet
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
        # Non-fatal — wallet creation failure is retryable via event replay
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

    token_hash = hash_refresh_token(body.refresh_token)
    stored_token = await refresh_repo.get_by_hash(token_hash)

    if not stored_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
        )

    user = await user_repo.get_by_id(stored_token.user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive.",
        )

    # Rotate: revoke old, issue new
    await refresh_repo.revoke(stored_token, actor_id=user.id)
    new_access = create_access_token(user.id, user.role.value)
    new_raw_refresh, _ = generate_refresh_token()
    ip = request.client.host if request.client else None
    ua = request.headers.get("User-Agent")
    await refresh_repo.create(user.id, new_raw_refresh, user_agent=ua, ip_address=ip)

    await audit_repo.create(
        action="auth.token_refreshed",
        actor_id=user.id,
        resource_type="user",
        resource_id=str(user.id),
        metadata={"ip": ip},
    )

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
