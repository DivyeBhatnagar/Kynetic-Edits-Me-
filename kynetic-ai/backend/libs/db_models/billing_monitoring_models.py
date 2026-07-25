"""
Phase 10 — India Billing, Monitoring & Launch Readiness ORM models.

Three tables:
  invoices        — GST-compliant invoices for Indian users (linked to transactions)
  notifications   — event-driven notifications per user (multi-channel)
  support_tickets — lightweight routing records for India-region support
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
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

class NotificationChannel(str, enum.Enum):
    email = "email"
    sms = "sms"
    push = "push"
    in_app = "in_app"


class NotificationType(str, enum.Enum):
    # Billing
    low_balance = "low_balance"
    wallet_topup_confirmed = "wallet_topup_confirmed"
    payout_confirmed = "payout_confirmed"
    invoice_ready = "invoice_ready"
    # Instance lifecycle
    instance_started = "instance_started"
    instance_stopped = "instance_stopped"
    instance_terminated = "instance_terminated"
    instance_failed = "instance_failed"
    # System
    system_alert = "system_alert"


class SupportTicketStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"


class SupportRegion(str, enum.Enum):
    india = "india"
    global_ = "global"


# ---------------------------------------------------------------------------
# Invoice — GST-compliant per-transaction invoice
# ---------------------------------------------------------------------------

class Invoice(Base):
    """
    GST-compliant invoice, generated for every completed billing event
    for Indian-region users. Linked to a transaction record.

    Design:
      - invoice_number follows sequential format e.g. KYN/2024-25/000001
      - gstin stores the user's GSTIN if provided (for B2B billing)
      - pdf_url points to S3-compatible object storage
      - PII stored minimally: just invoice_number, gstin, and amount; rest in transaction
    """
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # FK to wallet transactions table (marketplace_models.py)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallet_transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        unique=True,  # one invoice per transaction, idempotent
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Invoice metadata
    invoice_number: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)   # 15-digit Indian GSTIN
    # Financial fields — mirror transaction for invoice display without joining
    amount_inr: Mapped[str] = mapped_column(String(32), nullable=False)    # store as string to avoid float issues
    gst_rate_pct: Mapped[str] = mapped_column(String(8), nullable=False, default="18.00")
    gst_amount_inr: Mapped[str] = mapped_column(String(32), nullable=False)
    # PDF storage
    pdf_url: Mapped[str | None] = mapped_column(String(512), nullable=True)  # S3 URL, populated async
    # Timestamps
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<Invoice {self.invoice_number} user={self.user_id}>"


# ---------------------------------------------------------------------------
# Notification — event-driven per-user notifications
# ---------------------------------------------------------------------------

class Notification(Base):
    """
    Event-driven notification record. Written by the notifications_service
    Celery worker on lifecycle/billing events. Marked read by frontend.

    Channels: in_app (always), email (opt-in), sms/push (future).
    payload: JSONB blob with event-specific detail (e.g. {balance_usd: 0.50}).
    """
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType, name="notification_type_enum"),
        nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(
        Enum(NotificationChannel, name="notification_channel_enum"),
        nullable=False,
        default=NotificationChannel.in_app,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Dispatch state
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # created_at for ordering
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<Notification {self.notification_type} user={self.user_id} read={self.is_read}>"


# ---------------------------------------------------------------------------
# SupportTicket — lightweight India-first support routing
# ---------------------------------------------------------------------------

class SupportTicket(Base):
    """
    Lightweight support routing record. Stores enough to route tickets to
    the India support channel vs. global. The actual ticket body is handled
    by the external support tool (e.g. Freshdesk/Zendesk); this is the
    internal routing record as specified in the Phase 10 plan.
    """
    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region: Mapped[SupportRegion] = mapped_column(
        Enum(SupportRegion, name="support_region_enum"),
        nullable=False,
        default=SupportRegion.global_,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[SupportTicketStatus] = mapped_column(
        Enum(SupportTicketStatus, name="support_ticket_status_enum"),
        nullable=False,
        default=SupportTicketStatus.open,
    )
    external_ticket_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True  # ID from Freshdesk/Zendesk if integrated
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<SupportTicket {self.id} region={self.region} status={self.status}>"


# ---------------------------------------------------------------------------
# Notification preference (per-user channel opt-ins)
# ---------------------------------------------------------------------------

class NotificationPreference(Base):
    """
    Per-user notification preferences. One row per user.
    Created with defaults on user.created event.
    """
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    email_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sms_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    low_balance_threshold_usd: Mapped[str] = mapped_column(
        String(16), nullable=False, default="5.00"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<NotificationPreference user={self.user_id} email={self.email_enabled}>"


# ---------------------------------------------------------------------------
# InvoiceSequence — monotonic invoice number counter
# ---------------------------------------------------------------------------

class InvoiceSequence(Base):
    """
    Single-row counter for invoice number sequencing.
    KYN/{fiscal_year}/{seq:06d}  e.g. KYN/2024-25/000001

    One row per fiscal year. Incremented atomically in a serializable
    transaction to guarantee globally unique sequential numbers.
    """
    __tablename__ = "invoice_sequences"

    fiscal_year: Mapped[str] = mapped_column(
        String(10), primary_key=True  # e.g. "2024-25"
    )
    last_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:
        return f"<InvoiceSequence {self.fiscal_year} last={self.last_seq}>"
