"""
Alembic migration: 0003_marketplace_wallet

Creates:
  Enums:    resource_type_enum, listing_status_enum,
            transaction_type_enum (currency_enum already in 0002)
  Tables:   listings, wallets, wallet_transactions, stripe_accounts
  Indexes:  10 composite/partial indexes for marketplace query patterns

Depends on: 0002_host_onboarding (hosts + users tables)

upgrade:  create enums → create tables → create indexes
downgrade: drop tables → drop enums (reverse order)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0003"
down_revision: str = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    resource_type_enum = postgresql.ENUM(
        "gpu", "cpu", "ram", "nvme", "workstation_bundle",
        name="resource_type_enum",
    )
    resource_type_enum.create(op.get_bind(), checkfirst=True)

    listing_status_enum = postgresql.ENUM(
        "draft", "active", "paused", "delisted",
        name="listing_status_enum",
    )
    listing_status_enum.create(op.get_bind(), checkfirst=True)

    transaction_type_enum = postgresql.ENUM(
        "topup", "debit", "refund", "payout",
        name="transaction_type_enum",
    )
    transaction_type_enum.create(op.get_bind(), checkfirst=True)

    # currency_enum was already created in 0002 — reuse it here
    currency_enum = postgresql.ENUM(
        "usd", "inr",
        name="currency_enum",
    )
    currency_enum.create(op.get_bind(), checkfirst=True)

    # ── listings ──────────────────────────────────────────────────────────────
    op.create_table(
        "listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("host_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.Enum("gpu", "cpu", "ram", "nvme",
                  "workstation_bundle", name="resource_type_enum", create_type=False),
                  nullable=False),
        sa.Column("gpu_model", sa.String(200)),
        sa.Column("gpu_count", sa.Integer),
        sa.Column("gpu_vram_gb", sa.Numeric(10, 2)),
        sa.Column("cpu_cores", sa.Integer),
        sa.Column("ram_gb", sa.Numeric(10, 2)),
        sa.Column("storage_gb", sa.Numeric(10, 2)),
        sa.Column("storage_type", sa.String(20)),
        sa.Column("price_per_hour_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("price_per_hour_inr", sa.Numeric(12, 6), nullable=False),
        sa.Column("price_per_second_usd", sa.Numeric(18, 10), nullable=False),
        sa.Column("price_per_second_inr", sa.Numeric(18, 10), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("benchmark_scores", postgresql.JSONB),
        sa.Column("status", sa.Enum("draft", "active", "paused", "delisted",
                  name="listing_status_enum", create_type=False),
                  nullable=False, server_default="draft"),
        sa.Column("title", sa.String(200)),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("price_per_hour_usd >= 0", name="listing_price_usd_positive"),
        sa.CheckConstraint("price_per_hour_inr >= 0", name="listing_price_inr_positive"),
    )
    op.create_index("ix_listings_host_id", "listings", ["host_id"])
    op.create_index("ix_listings_owner_user_id", "listings", ["owner_user_id"])
    op.create_index("ix_listings_resource_type", "listings", ["resource_type"])
    op.create_index("ix_listings_status", "listings", ["status"])
    op.create_index("ix_listings_region", "listings", ["region"])
    op.create_index("ix_listings_gpu_model", "listings", ["gpu_model"])
    op.create_index("ix_listings_status_resource_type", "listings", ["status", "resource_type"])
    op.create_index("ix_listings_region_status", "listings", ["region", "status"])

    # ── wallets ───────────────────────────────────────────────────────────────
    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("balance_usd", sa.Numeric(18, 6), nullable=False,
                  server_default="0.000000"),
        sa.Column("balance_inr", sa.Numeric(18, 6), nullable=False,
                  server_default="0.000000"),
        sa.Column("preferred_currency",
                  sa.Enum("usd", "inr", name="currency_enum", create_type=False),
                  nullable=False, server_default="usd"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_wallets_user_id"),
        sa.CheckConstraint("balance_usd >= 0", name="wallet_balance_usd_non_negative"),
        sa.CheckConstraint("balance_inr >= 0", name="wallet_balance_inr_non_negative"),
    )
    op.create_index("ix_wallets_user_id", "wallets", ["user_id"])

    # ── wallet_transactions (IMMUTABLE) ───────────────────────────────────────
    op.create_table(
        "wallet_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("transaction_type",
                  sa.Enum("topup", "debit", "refund", "payout",
                          name="transaction_type_enum", create_type=False),
                  nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency",
                  sa.Enum("usd", "inr", name="currency_enum", create_type=False),
                  nullable=False),
        sa.Column("stripe_payment_intent_id", sa.String(200)),
        sa.Column("stripe_transfer_id", sa.String(200)),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True)),
        sa.Column("description", sa.String(500)),
        sa.Column("balance_after_usd", sa.Numeric(18, 6), nullable=False),
        sa.Column("balance_after_inr", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("amount > 0", name="txn_amount_positive"),
    )
    op.create_index("ix_wallet_txns_wallet_id", "wallet_transactions", ["wallet_id"])
    op.create_index("ix_wallet_txns_wallet_created", "wallet_transactions",
                    ["wallet_id", "created_at"])
    op.create_index("ix_wallet_txns_type", "wallet_transactions", ["transaction_type"])
    op.create_index("ix_wallet_txns_stripe_pi", "wallet_transactions",
                    ["stripe_payment_intent_id"])

    # ── stripe_accounts ───────────────────────────────────────────────────────
    op.create_table(
        "stripe_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stripe_customer_id", sa.String(200)),
        sa.Column("stripe_connect_account_id", sa.String(200)),
        sa.Column("connect_onboarding_complete", sa.Boolean, nullable=False,
                  server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_stripe_accounts_user_id"),
    )
    op.create_index("ix_stripe_accounts_user_id", "stripe_accounts", ["user_id"])
    op.create_index("ix_stripe_accounts_customer_id", "stripe_accounts", ["stripe_customer_id"])
    op.create_index("ix_stripe_accounts_connect_id", "stripe_accounts",
                    ["stripe_connect_account_id"])


def downgrade() -> None:
    # Tables in reverse dependency order
    op.drop_table("stripe_accounts")
    op.drop_table("wallet_transactions")
    op.drop_table("wallets")
    op.drop_table("listings")

    # Drop enums
    for enum_name in ("transaction_type_enum", "listing_status_enum",
                      "resource_type_enum", "currency_enum"):
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
