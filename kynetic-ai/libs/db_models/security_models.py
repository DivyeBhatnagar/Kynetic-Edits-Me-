"""
Security DB Models — Phase 5.

Tables:
  device_fingerprints — tracks device-level identity across signup/login
  trust_tiers         — per-user capability caps (instance size, GPU-hours, spend)
  security_event_logs — immutable record of all security-relevant events
  kill_switch_events  — audit trail for every kill-switch invocation

All tables have immutable audit fields (created_at, no soft-delete).
security_event_logs and kill_switch_events are append-only by convention —
no UPDATE or DELETE operations are issued against them anywhere in the codebase.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.db_models.models import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ── Enums ──────────────────────────────────────────────────────────────────

import enum


class TrustTierLevel(str, enum.Enum):
    """
    Trust tiers gate what compute resources a user can access.
    New accounts start at unverified. Phone-verified → tier1.
    ID-verified → tier2. Tier3 is manually granted by admins.
    """
    unverified = "unverified"  # brand-new account — strictest limits
    tier1      = "tier1"       # phone verified
    tier2      = "tier2"       # government ID verified
    tier3      = "tier3"       # admin-granted, no caps


class SecurityEventSeverity(str, enum.Enum):
    info     = "info"
    warning  = "warning"
    critical = "critical"


class SecurityEventType(str, enum.Enum):
    login_success           = "login_success"
    login_failure           = "login_failure"
    signup                  = "signup"
    device_fingerprint_new  = "device_fingerprint_new"
    device_fingerprint_match= "device_fingerprint_match"
    multi_account_suspected = "multi_account_suspected"
    crypto_mining_detected  = "crypto_mining_detected"
    image_scan_passed       = "image_scan_passed"
    image_scan_failed       = "image_scan_failed"
    wallet_fraud_suspected  = "wallet_fraud_suspected"
    wallet_topup_initiated  = "wallet_topup_initiated"   # Phase 5 audit
    payment_confirmed       = "payment_confirmed"         # Phase 5 audit
    kill_switch_triggered   = "kill_switch_triggered"
    trust_tier_change       = "trust_tier_change"
    rate_limit_exceeded     = "rate_limit_exceeded"
    abuse_blocked           = "abuse_blocked"


class KillSwitchTargetType(str, enum.Enum):
    instance = "instance"
    host     = "host"
    account  = "account"


# ── Tables ─────────────────────────────────────────────────────────────────

class DeviceFingerprint(Base):
    """
    Tracks unique device fingerprints per user.
    A fingerprint is computed from browser/client signals at signup/login.
    If the same fingerprint is seen on multiple user accounts, it's flagged
    as a multi-account abuse indicator.
    """
    __tablename__ = "device_fingerprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fingerprint_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="SHA-256 of browser/device signals. Never store raw signals."
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))  # IPv6-safe
    user_agent: Mapped[str | None] = mapped_column(Text)
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    seen_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "fingerprint_hash", name="uq_device_fp_user_hash"),
    )


class TrustTier(Base):
    """
    Per-user capability caps. Each user has exactly one row (upserted on change).

    Caps:
      max_instance_vcpus  — maximum vCPUs for a single instance
      max_gpu_vram_gb     — maximum GPU VRAM allowed
      max_gpu_hours_month — monthly GPU-hour cap
      max_spend_usd_month — monthly spend cap in USD

    NULL means "no cap" (only granted at tier3+admin).
    """
    __tablename__ = "trust_tiers"
    __table_args__ = (UniqueConstraint("user_id", name="uq_trust_tier_user"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier: Mapped[TrustTierLevel] = mapped_column(
        Enum(TrustTierLevel, name="trust_tier_level"),
        nullable=False,
        default=TrustTierLevel.unverified,
    )
    # Instance size caps
    max_instance_vcpus: Mapped[int | None] = mapped_column(Integer, default=2)
    max_gpu_vram_gb: Mapped[int | None] = mapped_column(Integer, default=None)
    # Monthly usage caps
    max_gpu_hours_month: Mapped[int | None] = mapped_column(Integer, default=10)
    max_spend_usd_month: Mapped[float | None] = mapped_column(
        Numeric(precision=12, scale=2), default=50.00
    )
    is_wallet_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class SecurityEventLog(Base):
    """
    Immutable audit log of all security-relevant events.
    Append-only — no UPDATE or DELETE is ever issued against this table.
    """
    __tablename__ = "security_event_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[SecurityEventType] = mapped_column(
        Enum(SecurityEventType, name="security_event_type"), nullable=False, index=True
    )
    severity: Mapped[SecurityEventSeverity] = mapped_column(
        Enum(SecurityEventSeverity, name="security_event_severity"),
        nullable=False,
        default=SecurityEventSeverity.info,
    )
    # Flexible resource reference
    resource_type: Mapped[str | None] = mapped_column(String(50))  # "user", "instance", "host", etc.
    resource_id: Mapped[str | None] = mapped_column(String(36), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )


class KillSwitchEvent(Base):
    """
    Immutable audit trail for every kill-switch invocation.
    Tied to admin actions only — no developer can trigger this directly.
    """
    __tablename__ = "kill_switch_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    target_type: Mapped[KillSwitchTargetType] = mapped_column(
        Enum(KillSwitchTargetType, name="kill_switch_target_type"), nullable=False
    )
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    triggered_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Result of the suspension broadcast
    broadcast_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
