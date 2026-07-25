"""
Alembic migration — Phase 10: India Billing, Unified Monitoring & Launch Readiness.

Creates:
  invoices                 — GST-compliant per-transaction invoices
  notifications            — event-driven per-user notifications
  notification_preferences — per-user channel opt-in settings
  support_tickets          — India-first support routing records
  invoice_sequences        — monotonic invoice number counter per fiscal year
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0010_billing_monitoring"
down_revision = "0008_reputation_pricing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── invoices ─────────────────────────────────────────────────────────────
    op.create_table(
        "invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "transaction_id",
            UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invoice_number", sa.String(64), nullable=False, unique=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("amount_inr", sa.String(32), nullable=False),
        sa.Column("gst_rate_pct", sa.String(8), nullable=False, server_default="18.00"),
        sa.Column("gst_amount_inr", sa.String(32), nullable=False),
        sa.Column("pdf_url", sa.String(512), nullable=True),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_invoices_transaction_id", "invoices", ["transaction_id"])
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])

    # ── invoice_sequences ─────────────────────────────────────────────────────
    op.create_table(
        "invoice_sequences",
        sa.Column("fiscal_year", sa.String(10), primary_key=True),
        sa.Column("last_seq", sa.Integer, nullable=False, server_default="0"),
    )

    # ── notification enums ────────────────────────────────────────────────────
    notification_type_enum = sa.Enum(
        "low_balance",
        "wallet_topup_confirmed",
        "payout_confirmed",
        "invoice_ready",
        "instance_started",
        "instance_stopped",
        "instance_terminated",
        "instance_failed",
        "system_alert",
        name="notification_type_enum",
    )
    notification_channel_enum = sa.Enum(
        "email", "sms", "push", "in_app",
        name="notification_channel_enum",
    )
    notification_type_enum.create(op.get_bind(), checkfirst=True)
    notification_channel_enum.create(op.get_bind(), checkfirst=True)

    # ── notifications ─────────────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("notification_type", notification_type_enum, nullable=False),
        sa.Column("channel", notification_channel_enum, nullable=False, server_default="in_app"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    # ── notification_preferences ──────────────────────────────────────────────
    op.create_table(
        "notification_preferences",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("email_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sms_enabled", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("low_balance_threshold_usd", sa.String(16), nullable=False, server_default="5.00"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_notification_prefs_user_id", "notification_preferences", ["user_id"])

    # ── support_tickets ───────────────────────────────────────────────────────
    support_region_enum = sa.Enum("india", "global", name="support_region_enum")
    support_ticket_status_enum = sa.Enum(
        "open", "in_progress", "resolved", "closed",
        name="support_ticket_status_enum",
    )
    support_region_enum.create(op.get_bind(), checkfirst=True)
    support_ticket_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "support_tickets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("region", support_region_enum, nullable=False, server_default="global"),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("status", support_ticket_status_enum, nullable=False, server_default="open"),
        sa.Column("external_ticket_id", sa.String(128), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])

    # ── User table: add gstin and region columns ───────────────────────────────
    # Allow users to store GSTIN for GST invoice generation
    op.add_column("users", sa.Column("gstin", sa.String(15), nullable=True))
    op.add_column("users", sa.Column("billing_region", sa.String(16), nullable=True, server_default="global"))


def downgrade() -> None:
    op.drop_column("users", "billing_region")
    op.drop_column("users", "gstin")

    op.drop_index("ix_support_tickets_user_id", table_name="support_tickets")
    op.drop_table("support_tickets")
    sa.Enum(name="support_ticket_status_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="support_region_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_index("ix_notification_prefs_user_id", table_name="notification_preferences")
    op.drop_table("notification_preferences")

    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    sa.Enum(name="notification_channel_enum").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notification_type_enum").drop(op.get_bind(), checkfirst=True)

    op.drop_table("invoice_sequences")

    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.drop_index("ix_invoices_user_id", table_name="invoices")
    op.drop_index("ix_invoices_transaction_id", table_name="invoices")
    op.drop_table("invoices")
