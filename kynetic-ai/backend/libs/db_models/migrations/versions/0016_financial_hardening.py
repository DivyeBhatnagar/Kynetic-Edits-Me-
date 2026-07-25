"""Phase 16 — Financial Operations & Compliance Hardening

Revision ID: 0016_financial_hardening
Revises: 0015_admin_operations
Create Date: 2026-07-24

Schema additions for Phase 16:
  - ledger_entries: double-entry accounting ledger (every transaction balances debit == credit)
  - chargebacks: Stripe/Razorpay payment dispute records and wallet freeze states
  - tax_withholdings: Indian TDS (Section 194O) and US 1099 tax withholding logs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0016_financial_hardening"
down_revision = "0015_admin_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── ledger_entries ────────────────────────────────────────────────────────
    op.create_table(
        "ledger_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account", sa.String(100), nullable=False,
                  comment="assets:stripe | assets:razorpay | liabilities:user_wallet | revenue:platform_fee | expenses:host_payout | liabilities:tds_withheld"),
        sa.Column("debit", sa.Numeric(14, 4), nullable=False, server_default="0.0000"),
        sa.Column("credit", sa.Numeric(14, 4), nullable=False, server_default="0.0000"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "idx_ledger_entries_txn_acc",
        "ledger_entries",
        ["transaction_id", "account"]
    )
    op.create_index(
        "idx_ledger_entries_created",
        "ledger_entries",
        ["created_at"]
    )

    # ── chargebacks ───────────────────────────────────────────────────────────
    op.create_table(
        "chargebacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(30), nullable=False,
                  comment="stripe | razorpay"),
        sa.Column("status", sa.String(30), nullable=False, server_default="opened",
                  comment="opened | under_review | won | lost"),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "idx_chargebacks_user_status",
        "chargebacks",
        ["user_id", "status"]
    )

    # ── tax_withholdings ──────────────────────────────────────────────────────
    op.create_table(
        "tax_withholdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payout_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("jurisdiction", sa.String(30), nullable=False,
                  comment="IN_TDS | US_1099"),
        sa.Column("gross_payout", sa.Numeric(12, 2), nullable=False),
        sa.Column("tax_rate_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("withheld_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("pan_or_tin", sa.String(50), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "idx_tax_withholdings_user_jurisdiction",
        "tax_withholdings",
        ["user_id", "jurisdiction", "issued_at"]
    )


def downgrade() -> None:
    op.drop_table("tax_withholdings")
    op.drop_table("chargebacks")
    op.drop_table("ledger_entries")
