"""Phase 12 — Infrastructure, Deployment & Environments

Revision ID: 0012_infrastructure
Revises: 0010_billing_monitoring
Create Date: 2026-07-24

Schema additions for Phase 12:
  - deployment_releases: tracks every deploy event (service, image tag, env, status)
  - environment_configs: key-value config store per environment (non-secret, audited)

Note: Secrets are NOT stored in the database — they live in AWS Secrets Manager/Vault.
      This table only tracks non-secret configuration and deploy audit history.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0012_infrastructure"
down_revision = "0010_billing_monitoring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── deployment_releases ───────────────────────────────────────────────────
    # Immutable audit log of every deployment event
    op.create_table(
        "deployment_releases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("service_name", sa.String(100), nullable=False),
        sa.Column("image_tag", sa.String(50), nullable=False,
                  comment="Short git SHA used for this deploy (e.g. abc12345)"),
        sa.Column("environment", sa.String(20), nullable=False,
                  comment="staging or production"),
        sa.Column("git_sha", sa.String(64), nullable=True),
        sa.Column("git_ref", sa.String(200), nullable=True,
                  comment="Branch or tag ref (e.g. refs/heads/main)"),
        sa.Column("deployed_by", sa.String(200), nullable=True,
                  comment="GitHub actor or username who triggered the deploy"),
        sa.Column("status", sa.String(20), nullable=False, server_default="started",
                  comment="started | success | failed | rolled_back"),
        sa.Column("started_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("migration_revision", sa.String(100), nullable=True,
                  comment="Alembic revision applied with this deploy"),
    )

    op.create_index(
        "idx_deployment_releases_env_service",
        "deployment_releases",
        ["environment", "service_name", "started_at"]
    )
    op.create_index(
        "idx_deployment_releases_status",
        "deployment_releases",
        ["status"]
    )

    # ── environment_configs ────────────────────────────────────────────────────
    # Non-secret per-environment configuration audit trail
    # Example: USD_TO_INR_RATE, RATE_LIMIT_REQUESTS_PER_MINUTE
    op.create_table(
        "environment_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("set_by", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True,
                  comment="Set when this key-value pair is replaced by a newer entry"),
    )

    op.create_index(
        "idx_environment_configs_lookup",
        "environment_configs",
        ["environment", "key", "superseded_at"]
    )

    # ── health_check_log ───────────────────────────────────────────────────────
    # Lightweight record of automated health check results for trending
    op.create_table(
        "service_health_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("service_name", sa.String(100), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  comment="healthy | degraded | unhealthy"),
        sa.Column("response_time_ms", sa.Integer, nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("details", postgresql.JSONB, nullable=True),
    )

    # Partial index — only keep recent records in the fast-path index
    op.create_index(
        "idx_service_health_recent",
        "service_health_checks",
        ["service_name", "environment", "checked_at"]
    )


def downgrade() -> None:
    op.drop_table("service_health_checks")
    op.drop_table("environment_configs")
    op.drop_table("deployment_releases")
