"""Phase 15 — Admin Panel & Internal Operations Tooling

Revision ID: 0015_admin_operations
Revises: 0013_observability
Create Date: 2026-07-24

Schema additions for Phase 15:
  - admin_users: SSO-authenticated internal admin user accounts and RBAC roles
  - ticket_activity_logs: support ticket resolution history log
  - fraud_review_queue: flagged user/host trust and security review items
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0015_admin_operations"
down_revision = "0013_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── admin_users ───────────────────────────────────────────────────────────
    op.create_table(
        "admin_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("role", sa.String(30), nullable=False,
                  comment="support | finance | security | superadmin"),
        sa.Column("sso_subject", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("idx_admin_users_email", "admin_users", ["email"])
    op.create_index("idx_admin_users_role", "admin_users", ["role"])

    # ── ticket_activity_logs ──────────────────────────────────────────────────
    op.create_table(
        "ticket_activity_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(30), nullable=False,
                  comment="assigned | responded | resolved | escalated"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "idx_ticket_activity_ticket",
        "ticket_activity_logs",
        ["ticket_id", "created_at"]
    )

    # ── fraud_review_queue ────────────────────────────────────────────────────
    op.create_table(
        "fraud_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("host_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("risk_score", sa.Integer, nullable=False, server_default="50"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending",
                  comment="pending | approved | rejected | suspended"),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "idx_fraud_queue_status_risk",
        "fraud_review_queue",
        ["status", "risk_score", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("fraud_review_queue")
    op.drop_table("ticket_activity_logs")
    op.drop_table("admin_users")
