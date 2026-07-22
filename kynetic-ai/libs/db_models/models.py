"""
Phase 1 database models: users, sessions/refresh_tokens, audit_logs.

Design principles:
- All PKs are UUIDs (uuid4) — avoids enumerable IDs in API responses.
- audit_logs is IMMUTABLE / append-only at the application layer —
  no UPDATE or DELETE is ever performed on this table.
- created_at / updated_at are set server-side to avoid clock skew.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.db_models.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class UserRole(str, enum.Enum):
    """An account can be a host, a developer, or both."""
    HOST = "host"
    DEVELOPER = "developer"
    BOTH = "both"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class User(Base):
    """
    Central user record — created by Auth Service on signup.
    Supports both host and developer roles on a single account.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role"), nullable=False, default=UserRole.DEVELOPER
    )
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships (resolved in later phases)
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken", back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship("AuditLog", back_populates="actor")

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


# ---------------------------------------------------------------------------
# Refresh Tokens
# ---------------------------------------------------------------------------
class RefreshToken(Base):
    """
    Opaque refresh token record — enables JWT refresh token rotation.
    On refresh: the old token is revoked, a new one is issued.
    Only one active token per user per device (family token invalidation on theft).
    """
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True,
        comment="SHA-256 hash of the raw token value — never store raw token"
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens")

    __table_args__ = (
        Index("ix_refresh_tokens_user_active", "user_id", "is_revoked"),
    )

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.is_revoked}>"


# ---------------------------------------------------------------------------
# Phone OTP
# ---------------------------------------------------------------------------
class PhoneOTP(Base):
    """
    Short-lived OTP record for phone number verification.
    Expires after PHONE_OTP_TTL_SECONDS (default 10 minutes).
    Max 3 verification attempts before the OTP is invalidated.
    """
    __tablename__ = "phone_otps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    otp_hash: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Bcrypt/argon2 hash of the 6-digit OTP — never store raw OTP"
    )
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_phone_otps_user_active", "user_id", "is_used", "expires_at"),
    )


# ---------------------------------------------------------------------------
# Audit Logs — IMMUTABLE, APPEND-ONLY
# ---------------------------------------------------------------------------
class AuditLog(Base):
    """
    Immutable audit trail for every write action across all services.

    CRITICAL: No UPDATE or DELETE is ever executed on this table at the
    application layer. This is enforced by the repository pattern —
    only `AuditLogRepository.create()` exists; no update/delete methods.

    Per the Security Architecture (Pillar 11), audit logs are separated
    by purpose:
    - General write actions → audit_logs (this table)
    - Security events       → security_event_logs (Phase 5)
    - Admin actions         → admin_action_logs (Phase 5)
    """
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="NULL for system/anonymous actions",
    )
    action: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True,
        comment="snake_case event name, e.g. user.signup, listing.created"
    )
    resource_type: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="e.g. 'user', 'listing', 'instance'"
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="UUID or string identifier of the affected resource"
    )
    extra_data: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Additional context — IP, user-agent, diff, etc."
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    actor: Mapped["User | None"] = relationship("User", back_populates="audit_logs")

    __table_args__ = (
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AuditLog id={self.id} action={self.action} "
            f"actor={self.actor_id} resource={self.resource_type}:{self.resource_id}>"
        )
