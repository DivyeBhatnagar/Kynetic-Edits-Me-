"""
Provisioning DB Models (Phase 4).

Tables:
  instances               — compute instance lifecycle records
  ssh_sessions            — ephemeral keypairs per instance session
  secure_deletion_receipts — cryptographic deletion audit trail

Enum:
  InstanceStatus — pending | provisioning | running | stopping |
                   stopped | terminated | failed
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from libs.db_models.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────

class InstanceStatus(str, enum.Enum):
    pending       = "pending"        # Request received, wallet hold placed
    provisioning  = "provisioning"   # Celery task dispatched to host agent
    running       = "running"        # VM up, billing active
    stopping      = "stopping"       # Stop command sent, VM suspending
    stopped       = "stopped"        # VM suspended, billing paused
    terminated    = "terminated"     # VM deleted, volume shredded, hold released
    failed        = "failed"         # Unrecoverable error; hold released


# ── Models ─────────────────────────────────────────────────────────────────

class Instance(Base):
    """
    Represents one compute rental session.

    State machine (enforced at repository layer):
      pending → provisioning → running → stopping → stopped
                                       ↘ terminated
                                       ↘ failed
      Any state → terminated (force-terminate is always allowed)

    CRITICAL: Only `InstanceRepository.transition_state()` may change
    `status`. All application code must go through this method, which
    validates the transition is legal before writing.
    """
    __tablename__ = "instances"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    developer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Template (Phase 6) ─────────────────────────────────────────────────
    # Nullable — instances launched without a template_id are raw/custom launches.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Phase 6: template used for one-click launch (NULL = raw launch)",
    )
    template: Mapped["Template | None"] = relationship(
        "Template",
        back_populates="instances",
        lazy="noload",
    )

    status: Mapped[InstanceStatus] = mapped_column(
        Enum(InstanceStatus, name="instance_status_enum", create_type=True),
        nullable=False,
        default=InstanceStatus.pending,
        index=True,
    )

    # ── Financial hold ─────────────────────────────────────────────────────
    # A hold equal to 1 hour of compute is debited upfront; per-second billing
    # happens concurrently. On termination, unused hold is refunded.
    hold_amount: Mapped[float] = mapped_column(
        Numeric(16, 6), nullable=False,
        comment="Wallet hold placed at launch time (USD)"
    )
    hold_released: Mapped[bool] = mapped_column(
        default=False, nullable=False,
        comment="True once hold has been refunded on termination"
    )

    # ── Resource Allocation ───────────────────────────────────────────────
    image: Mapped[str] = mapped_column(
        String(255), nullable=False, default="ubuntu:22.04",
        comment="Base OCI image tag"
    )
    cpu_allocated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2
    )
    ram_gb_allocated: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=4.0
    )
    gpu_allocated: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    vram_gb_allocated: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    workspace_path: Mapped[str | None] = mapped_column(
        String(500), nullable=True,
        comment="Local workspace volume path on host machine"
    )

    # ── Agent info ─────────────────────────────────────────────────────────
    firecracker_vm_id: Mapped[str | None] = mapped_column(
        String(100),
        comment="Firecracker VM ID returned by host agent"
    )
    container_id: Mapped[str | None] = mapped_column(
        String(100),
        comment="Docker container ID inside the microVM"
    )
    agent_host_url: Mapped[str | None] = mapped_column(
        String(500),
        comment="mTLS URL of the host agent (stored at launch time)"
    )

    # ── WireGuard / network ────────────────────────────────────────────────
    wireguard_ip: Mapped[str | None] = mapped_column(
        String(20),
        comment="WireGuard VPN IP allocated for this instance's relay"
    )
    public_ip: Mapped[str | None] = mapped_column(
        String(50),
        comment="Host's public IP if directly reachable (else None → use WireGuard)"
    )
    ssh_port: Mapped[int] = mapped_column(
        Integer, default=22, nullable=False
    )

    # ── Billing counters ───────────────────────────────────────────────────
    billed_seconds: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False,
        comment="Monotonically increasing counter updated by billing watcher"
    )
    price_per_second_usd: Mapped[float] = mapped_column(
        Numeric(20, 10), nullable=False,
        comment="Snapshot of listing rate at launch time"
    )

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        comment="When instance transitioned to running"
    )
    stopped_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    terminated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    __table_args__ = (
        Index("ix_instances_developer_status", "developer_id", "status"),
        Index("ix_instances_host_status", "host_id", "status"),
        # Partial index: only running instances (billing watcher queries)
        Index(
            "ix_instances_running",
            "id",
            postgresql_where="status = 'running'",
        ),
        CheckConstraint("billed_seconds >= 0", name="ck_instances_billed_seconds_nonneg"),
        CheckConstraint("hold_amount >= 0", name="ck_instances_hold_amount_nonneg"),
    )


class SSHSession(Base):
    """
    Ephemeral SSH keypair for one instance session.

    Security rules:
    - Private key is NEVER stored in plaintext. It is encrypted with
      Fernet (symmetric AES-128-CBC + HMAC-SHA256) before INSERT.
    - Only the provisioning service holds the Fernet key (env var).
    - On revocation (instance terminated), private_key_encrypted is
      overwritten with NULL — the plaintext is unrecoverable.
    - The public key is injected into the isolated container's
      authorized_keys; only that specific instance accepts the key.
    """
    __tablename__ = "ssh_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # One active SSH session per instance at a time
        index=True,
    )

    # RSA-4096 public key (safe to store plaintext — only used for injection)
    public_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Fernet-encrypted private key. NULL after instance termination.
    private_key_encrypted: Mapped[str | None] = mapped_column(
        Text,
        comment="Fernet(private_key_pem). Nulled on revocation."
    )

    # Relay details (populated if WireGuard relay is used)
    relay_host: Mapped[str | None] = mapped_column(String(255))
    relay_port: Mapped[int | None] = mapped_column(Integer)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now()
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SecureDeletionReceipt(Base):
    """
    Cryptographic proof that ephemeral storage was destroyed after
    instance termination. Required for Security Pillar 1 compliance.

    Written by: `terminate_instance` Celery task after the host agent
    confirms deletion via its /agent/verify_deletion callback.

    IMMUTABLE: no UPDATE or DELETE is ever executed on this table.
    """
    __tablename__ = "secure_deletion_receipts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,   # One receipt per instance
        index=True,
    )

    # How the data was destroyed
    method: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="e.g. 'luks_key_destruction', 'dod_overwrite', 'mock_shred'"
    )

    # Hash returned by the host agent as proof
    agent_confirmation_hash: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="SHA-256 hash of deletion confirmation payload from agent"
    )

    # Timestamp the provisioning service received and recorded the receipt
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now()
    )

    # Raw agent callback payload for audit
    agent_payload: Mapped[str | None] = mapped_column(
        Text,
        comment="Raw JSON from agent /agent/verify_deletion response"
    )


class InstanceEvent(Base):
    """
    Audit trail for instance lifecycle state changes and provisioning events.
    """
    __tablename__ = "instance_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now()
    )

