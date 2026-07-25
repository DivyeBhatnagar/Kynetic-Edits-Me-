"""
Database Models — Implementation Plan v7 Payment & Webhook Entities (payment_models_v7.py)

Tables:
- orders: tracks payment creation requests
- payments: tracks captured payments
- webhook_events: incoming provider webhooks with UNIQUE constraint on provider_event_id for database-level replay protection
"""

import uuid
from datetime import datetime, timezone
import enum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from libs.db_models.database import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class OrderStatus(str, enum.Enum):
    created = "created"
    paid    = "paid"
    failed  = "failed"
    expired = "expired"


class PaymentStatus(str, enum.Enum):
    captured = "captured"
    failed   = "failed"
    refunded = "refunded"


class WebhookStatus(str, enum.Enum):
    received  = "received"
    processed = "processed"
    failed    = "failed"


class Order(Base):
    __tablename__ = "v7_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_order_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), default="wallet_topup", nullable=False)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus, name="v7_order_status"), default=OrderStatus.created, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Payment(Base):
    __tablename__ = "v7_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v7_orders.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_payment_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="v7_payment_status"), default=PaymentStatus.captured, nullable=False)
    method: Mapped[str] = mapped_column(String(50), default="card", nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class WebhookEvent(Base):
    """
    Incoming provider webhooks.
    Enforces DB-level replay protection via uq_webhook_provider_event_id.
    """
    __tablename__ = "v7_webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_webhook_provider_event_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[WebhookStatus] = mapped_column(Enum(WebhookStatus, name="v7_webhook_status"), default=WebhookStatus.received, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LedgerEntryType(str, enum.Enum):
    debit              = "debit"
    credit             = "credit"
    customer_payment   = "customer_payment"
    host_earnings      = "host_earnings"
    platform_commission= "platform_commission"
    refund             = "refund"
    payout             = "payout"


class LedgerEntry(Base):
    """
    Append-only double-entry financial ledger (§7).
    """
    __tablename__ = "v7_ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entry_type: Mapped[LedgerEntryType] = mapped_column(Enum(LedgerEntryType, name="v7_ledger_entry_type"), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class KYCStatus(str, enum.Enum):
    pending  = "pending"
    approved = "approved"
    rejected = "rejected"


class ProviderAccountStatus(str, enum.Enum):
    pending   = "pending"
    active    = "active"
    suspended = "suspended"


class HostEarningsStatus(str, enum.Enum):
    pending_settlement = "pending_settlement"
    settled            = "settled"
    held               = "held"
    reversed           = "reversed"


class CommissionScope(str, enum.Enum):
    global_default = "global"
    host           = "host"
    enterprise     = "enterprise"
    promotional    = "promotional"
    gpu_type       = "gpu_type"
    region         = "region"
    workload       = "workload"


class HostKYCRecord(Base):
    """
    Host identity and bank verification details (§6, §13).
    Sensitive data (PAN, bank account numbers) encrypted at application layer.
    """
    __tablename__ = "v7_host_kyc_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    pan_number_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    pan_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    bank_account_number_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    ifsc_code: Mapped[str] = mapped_column(String(20), nullable=False)
    bank_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    upi_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    document_urls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[KYCStatus] = mapped_column(Enum(KYCStatus, name="v7_kyc_status"), default=KYCStatus.pending, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentProviderAccount(Base):
    """
    Provider linked account identifier for delayed transfers (§6, §14).
    """
    __tablename__ = "v7_payment_provider_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    linked_account_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    account_status: Mapped[ProviderAccountStatus] = mapped_column(Enum(ProviderAccountStatus, name="v7_provider_account_status"), default=ProviderAccountStatus.active, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CommissionRule(Base):
    """
    Priority-based commission rules (§9). Lower priority number = evaluated first.
    """
    __tablename__ = "v7_commission_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[CommissionScope] = mapped_column(Enum(CommissionScope, name="v7_commission_scope"), nullable=False, index=True)
    scope_ref_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    commission_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    priority: Mapped[int] = mapped_column(default=100, nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HostEarnings(Base):
    """
    Accrued host earnings from completed compute rentals pending payout (§6).
    """
    __tablename__ = "v7_host_earnings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    billing_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    gross_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    commission_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    commission_rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("v7_commission_rules.id", ondelete="SET NULL"), nullable=True)
    net_amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[HostEarningsStatus] = mapped_column(Enum(HostEarningsStatus, name="v7_host_earnings_status"), default=HostEarningsStatus.pending_settlement, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayoutStatus(str, enum.Enum):
    scheduled      = "scheduled"
    processing     = "processing"
    completed      = "completed"
    failed         = "failed"
    retrying       = "retrying"
    manual_review  = "manual_review"


class RefundStatus(str, enum.Enum):
    pending   = "pending"
    processed = "processed"
    failed    = "failed"


class Payout(Base):
    """
    Host settlement payout batch (§6, §15).
    """
    __tablename__ = "v7_payouts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    host_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True)
    payout_cycle: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[PayoutStatus] = mapped_column(Enum(PayoutStatus, name="v7_payout_status"), default=PayoutStatus.scheduled, nullable=False)
    provider_transfer_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PayoutLineItem(Base):
    """
    Join table linking payouts to host earnings (§6, §15).
    """
    __tablename__ = "v7_payout_line_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v7_payouts.id", ondelete="CASCADE"), nullable=False, index=True)
    host_earnings_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v7_host_earnings.id", ondelete="CASCADE"), nullable=False, index=True)


class Settlement(Base):
    """
    Provider settlement reconciliation receipt (§6, §15).
    """
    __tablename__ = "v7_settlements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v7_payouts.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_settlement_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    provider_fee: Mapped[float] = mapped_column(Numeric(10, 4), default=0.0, nullable=False)
    net_settled_amount: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    settled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class Refund(Base):
    """
    Customer refund requests (§6, §18).
    """
    __tablename__ = "v7_refunds"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("v7_payments.id", ondelete="CASCADE"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RefundStatus] = mapped_column(Enum(RefundStatus, name="v7_refund_status"), default=RefundStatus.pending, nullable=False)
    provider_refund_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


