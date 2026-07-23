"""
Auth Service — Repository layer (DB access abstraction).

All DB operations go through repository classes, not raw session calls in routes.
This keeps routes thin, makes testing easier (mock the repo, not the DB),
and ensures audit log writes happen consistently alongside every mutation.

Repository pattern enforces the immutability rule:
- AuditLogRepository has only `create()` — no update/delete methods exist.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import AuditLog, PhoneOTP, RefreshToken, User, UserRole
from services.auth_service.security import (
    generate_otp,
    hash_otp,
    hash_password,
    hash_refresh_token,
    refresh_token_expires_at,
)

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Audit Log Repository — append-only
# ---------------------------------------------------------------------------
class AuditLogRepository:
    """Append-only repository for the audit_logs table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        action: str,
        actor_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            metadata=metadata,
        )
        self.session.add(log)
        await self.session.flush()  # Get the ID without committing
        logger.debug("audit_log_created", action=action, actor_id=str(actor_id))
        return log


# ---------------------------------------------------------------------------
# User Repository
# ---------------------------------------------------------------------------
class UserRepository:
    def __init__(self, session: AsyncSession, audit_repo: AuditLogRepository) -> None:
        self.session = session
        self.audit = audit_repo

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        email: str,
        plain_password: str,
        role: UserRole = UserRole.DEVELOPER,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            hashed_password=hash_password(plain_password),
            role=role,
        )
        self.session.add(user)
        await self.session.flush()  # Populates user.id

        await self.audit.create(
            action="user.signup",
            actor_id=user.id,
            resource_type="user",
            resource_id=str(user.id),
            metadata={"email": user.email, "role": role.value, "ip": ip_address},
        )
        logger.info("user_created", user_id=str(user.id), email=user.email, role=role.value)
        return user

    async def mark_phone_verified(self, user_id: uuid.UUID, phone_number: str) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(phone_number=phone_number, phone_verified=True)
        )
        await self.audit.create(
            action="user.phone_verified",
            actor_id=user_id,
            resource_type="user",
            resource_id=str(user_id),
            metadata={"phone_number": phone_number},
        )


# ---------------------------------------------------------------------------
# Refresh Token Repository
# ---------------------------------------------------------------------------
class RefreshTokenRepository:
    def __init__(self, session: AsyncSession, audit_repo: AuditLogRepository) -> None:
        self.session = session
        self.audit = audit_repo

    async def create(
        self,
        user_id: uuid.UUID,
        raw_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshToken:
        token = RefreshToken(
            user_id=user_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=refresh_token_expires_at(),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.session.add(token)
        await self.session.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked == False,  # noqa: E712
                RefreshToken.expires_at > datetime.now(UTC),
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, token: RefreshToken, actor_id: uuid.UUID) -> None:
        token.is_revoked = True
        token.revoked_at = datetime.now(UTC)
        await self.audit.create(
            action="auth.refresh_token_revoked",
            actor_id=actor_id,
            resource_type="refresh_token",
            resource_id=str(token.id),
        )

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke all active refresh tokens for a user — used on logout."""
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.is_revoked == False)  # noqa: E712
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.audit.create(
            action="auth.logout_all_tokens_revoked",
            actor_id=user_id,
            resource_type="user",
            resource_id=str(user_id),
        )


# ---------------------------------------------------------------------------
# Phone OTP Repository
# ---------------------------------------------------------------------------
class PhoneOTPRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: uuid.UUID, phone_number: str) -> tuple["PhoneOTP", str]:
        """
        Create a new OTP record.
        Returns (otp_record, raw_otp) — raw OTP sent to user via SMS, hash stored in DB.
        """
        from datetime import timedelta
        from services.auth_service.config import get_settings as _get_settings
        _settings = _get_settings()

        raw_otp = generate_otp()
        otp_record = PhoneOTP(
            user_id=user_id,
            phone_number=phone_number,
            otp_hash=hash_otp(raw_otp),
            expires_at=datetime.now(UTC) + timedelta(seconds=_settings.phone_otp_ttl_seconds),
        )
        self.session.add(otp_record)
        await self.session.flush()
        return otp_record, raw_otp

    async def get_active(self, user_id: uuid.UUID, phone_number: str) -> "PhoneOTP | None":
        result = await self.session.execute(
            select(PhoneOTP).where(
                PhoneOTP.user_id == user_id,
                PhoneOTP.phone_number == phone_number,
                PhoneOTP.is_used == False,  # noqa: E712
                PhoneOTP.expires_at > datetime.now(UTC),
            ).order_by(PhoneOTP.created_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, otp: "PhoneOTP") -> None:
        otp.is_used = True

    async def increment_attempts(self, otp: "PhoneOTP") -> None:
        otp.attempts += 1
