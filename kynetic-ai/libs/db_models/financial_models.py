"""
Phase 16 — Financial Operations & Compliance Hardening ORM Models

Three tables:
  ledger_entries  — double-entry accounting ledger (every transaction balances debit == credit)
  chargebacks     — Stripe & Razorpay payment dispute tracking and wallet freeze status
  tax_withholdings — Indian TDS (Sec 194O) and US 1099 tax withholding log
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from libs.db_models.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChargebackStatus(str, enum.Enum):
    opened       = "opened"
    under_review = "under_review"
    won          = "won"
    lost         = "lost"


class TaxJurisdiction(str, enum.Enum):
    in_tds  = "IN_TDS"
    us_1099 = "US_1099"


# ---------------------------------------------------------------------------
# LedgerEntry — double-entry accounting ledger
# ---------------------------------------------------------------------------

class LedgerEntry(Base):
    """
    Immutable double-entry accounting log.
    Every financial event creates at least two balancing entries where sum(debit) == sum(credit).
    """
    __tablename__ = "ledger_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    account: Mapped[str] = mapped_column(String(100), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0.0000"))
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=Decimal("0.0000"))
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_ledger_entries_txn_acc", "transaction_id", "account"),
        Index("idx_ledger_entries_created", "created_at"),
    )


# ---------------------------------------------------------------------------
# Chargeback — payment dispute tracking
# ---------------------------------------------------------------------------

class Chargeback(Base):
    """
    Payment chargeback / dispute record for Stripe and Razorpay events.
    """
    __tablename__ = "chargebacks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[ChargebackStatus] = mapped_column(
        Enum(ChargebackStatus, name="chargeback_status"),
        nullable=False,
        default=ChargebackStatus.opened
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_chargebacks_user_status", "user_id", "status"),
    )


# ---------------------------------------------------------------------------
# TaxWithholding — TDS and 1099 tax withholding logs
# ---------------------------------------------------------------------------

class TaxWithholding(Base):
    """
    Tax withholding record for host payouts (Section 194O TDS for India, 1099 for US).
    """
    __tablename__ = "tax_withholdings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    jurisdiction: Mapped[TaxJurisdiction] = mapped_column(
        Enum(TaxJurisdiction, name="tax_jurisdiction"),
        nullable=False
    )
    gross_payout: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    tax_rate_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    withheld_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    pan_or_tin: Mapped[str | None] = mapped_column(String(50), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_tax_withholdings_user_jurisdiction", "user_id", "jurisdiction", "issued_at"),
    )
