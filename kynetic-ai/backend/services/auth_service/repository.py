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

from libs.db_models.user_models import (
    ApiToken,
    AuditLog,
    DeviceCode,
    DeviceCodeStatus,
    Event,
    PhoneOTP,
    RefreshToken,
    Session,
    User,
    UserRole,
)
from services.auth_service.security import (
    generate_otp,
    hash_otp,
    hash_password,
    hash_refresh_token,
    refresh_token_expires_at,
)

logger = structlog.get_logger(__name__)


import hashlib

# ---------------------------------------------------------------------------
# Audit Log Repository — append-only with hash-chaining
# ---------------------------------------------------------------------------
class AuditLogRepository:
    """Append-only repository for the audit_logs table with SHA-256 hash-chaining."""

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
        # Fetch latest entry_hash to form the hash chain
        stmt = select(AuditLog.entry_hash).order_by(AuditLog.created_at.desc()).limit(1)
        res = await self.session.execute(stmt)
        last_hash = res.scalar_one_or_none()
        prev_hash = last_hash or "GENESIS_HASH_CHAIN_ROOT_0000000000000000000000000000000000000000"

        now_str = datetime.now(UTC).isoformat()
        payload = f"{prev_hash}|{now_str}|{actor_id}|{action}|{resource_type}|{resource_id}"
        entry_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        log = AuditLog(
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            extra_data=metadata,
            prev_hash=prev_hash,
            entry_hash=entry_hash,
        )
        self.session.add(log)
        await self.session.flush()  # Get the ID without committing
        logger.debug("audit_log_created", action=action, actor_id=str(actor_id), entry_hash=entry_hash)
        return log


# ---------------------------------------------------------------------------
# Event Repository — append-only
# ---------------------------------------------------------------------------
class EventRepository:
    """Append-only repository for the events table."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        event_type: str,
        actor_id: uuid.UUID | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        metadata: dict | None = None,
    ) -> Event:
        event = Event(
            actor_id=actor_id,
            event_type=event_type,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            event_metadata=metadata,
        )
        self.session.add(event)
        await self.session.flush()
        return event


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
# Refresh Token & Session Repository (Single-use Token Family Rotation)
# ---------------------------------------------------------------------------
class RefreshTokenRepository:
    def __init__(self, session: AsyncSession, audit_repo: AuditLogRepository) -> None:
        self.session = session
        self.audit = audit_repo

    async def create(
        self,
        user_id: uuid.UUID,
        raw_token: str,
        family_id: uuid.UUID | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshToken:
        actual_family_id = family_id or uuid.uuid4()
        token = RefreshToken(
            user_id=user_id,
            family_id=actual_family_id,
            token_hash=hash_refresh_token(raw_token),
            expires_at=refresh_token_expires_at(),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self.session.add(token)

        # Also register in sessions table
        user_session = Session(
            user_id=user_id,
            refresh_token_hash=hash_refresh_token(raw_token),
            device_label=user_agent[:250] if user_agent else "CLI/Web Device",
            expires_at=refresh_token_expires_at(),
        )
        self.session.add(user_session)

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

    async def rotate(
        self,
        raw_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> tuple[str, RefreshToken] | None:
        """
        Rotates a single-use refresh token.
        If the token has already been used (reuse detection), revokes the ENTIRE token family.
        """
        token_hash = hash_refresh_token(raw_token)
        result = await self.session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.expires_at > datetime.now(UTC),
            )
        )
        token = result.scalar_one_or_none()
        if not token:
            return None

        # Check if already revoked or already used -> REUSE COMPROMISE DETECTED
        if token.is_revoked or token.used_at is not None:
            logger.warning(
                "refresh_token_reuse_detected",
                token_id=str(token.id),
                user_id=str(token.user_id),
                family_id=str(token.family_id),
            )
            # Revoke entire token family
            await self.revoke_family(token.family_id, token.user_id, reason="reuse_detection")
            return None

        # Mark current token as used
        token.used_at = datetime.now(UTC)

        from services.auth_service.security import generate_refresh_token
        new_raw_token, new_token_hash = generate_refresh_token()
        token.replaced_by_hash = new_token_hash

        new_token = RefreshToken(
            user_id=token.user_id,
            family_id=token.family_id,
            token_hash=new_token_hash,
            expires_at=refresh_token_expires_at(),
            user_agent=user_agent or token.user_agent,
            ip_address=ip_address or token.ip_address,
        )
        self.session.add(new_token)

        # Update session
        user_session = Session(
            user_id=token.user_id,
            refresh_token_hash=new_token_hash,
            device_label=(user_agent[:250] if user_agent else token.user_agent[:250]) if (user_agent or token.user_agent) else "CLI/Web Device",
            expires_at=refresh_token_expires_at(),
        )
        self.session.add(user_session)

        await self.session.flush()

        await self.audit.create(
            action="auth.refresh_token_rotated",
            actor_id=token.user_id,
            resource_type="refresh_token",
            resource_id=str(new_token.id),
            metadata={"family_id": str(token.family_id)},
        )

        return new_raw_token, new_token

    async def revoke_family(
        self,
        family_id: uuid.UUID,
        user_id: uuid.UUID,
        reason: str = "security_revocation",
    ) -> None:
        """Revokes all tokens in a family due to replay/compromise detection."""
        await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.is_revoked == False)  # noqa: E712
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.audit.create(
            action="auth.token_family_revoked",
            actor_id=user_id,
            resource_type="token_family",
            resource_id=str(family_id),
            metadata={"reason": reason},
        )

    async def revoke(self, token: RefreshToken, actor_id: uuid.UUID) -> None:
        token.is_revoked = True
        token.revoked_at = datetime.now(UTC)

        # Revoke session matching refresh_token_hash
        await self.session.execute(
            update(Session)
            .where(Session.refresh_token_hash == token.token_hash, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )

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
        await self.session.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.audit.create(
            action="auth.logout_all_tokens_revoked",
            actor_id=user_id,
            resource_type="user",
            resource_id=str(user_id),
        )


# ---------------------------------------------------------------------------
# Device Code Repository (RFC 8628)
# ---------------------------------------------------------------------------
class DeviceCodeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_agent: str | None = None,
        ip_address: str | None = None,
        expires_in_seconds: int = 600,
    ) -> DeviceCode:
        import secrets
        from datetime import timedelta

        # Generate unique RFC 8628 codes
        raw_device_code = secrets.token_urlsafe(32)
        part1 = secrets.choice("BCDFGHJKLMNPQRSTVWXYZ") + secrets.choice("BCDFGHJKLMNPQRSTVWXYZ") + secrets.choice("23456789") + secrets.choice("23456789")
        part2 = secrets.choice("BCDFGHJKLMNPQRSTVWXYZ") + secrets.choice("BCDFGHJKLMNPQRSTVWXYZ") + secrets.choice("23456789") + secrets.choice("23456789")
        user_code = f"{part1}-{part2}"

        code_record = DeviceCode(
            device_code=raw_device_code,
            user_code=user_code,
            status=DeviceCodeStatus.PENDING,
            user_agent=user_agent,
            ip_address=ip_address,
            expires_at=datetime.now(UTC) + timedelta(seconds=expires_in_seconds),
        )
        self.session.add(code_record)
        await self.session.flush()
        return code_record

    async def get_by_device_code(self, device_code: str) -> DeviceCode | None:
        result = await self.session.execute(
            select(DeviceCode).where(DeviceCode.device_code == device_code)
        )
        return result.scalar_one_or_none()

    async def get_by_user_code(self, user_code: str) -> DeviceCode | None:
        formatted_code = user_code.upper().strip()
        result = await self.session.execute(
            select(DeviceCode).where(DeviceCode.user_code == formatted_code)
        )
        return result.scalar_one_or_none()

    async def approve(self, code_record: DeviceCode, user_id: uuid.UUID) -> None:
        code_record.status = DeviceCodeStatus.APPROVED
        code_record.user_id = user_id

    async def deny(self, code_record: DeviceCode) -> None:
        code_record.status = DeviceCodeStatus.DENIED


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

