"""
Phase 28 — DB Migration: billing_meter_jobs

Adds the table that tracks one active per-second billing metering job
per running instance. Required for:
  - Knowing which Celery task to revoke when an instance terminates
  - Reconciliation sweep (finding instances without an active metering job)
  - Audit: how long was an instance actively billed?

Migration ID: 0012_billing_meter_jobs
Depends on: 0004_instances (for instances.id FK)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "billing_meter_jobs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "celery_task_id",
            sa.String(200),
            nullable=False,
            comment="Task ID of the active debit_running_instance Celery chain",
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_debited_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "stopped_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Set when metering stops (INSTANCE_TERMINATED event)",
        ),
        sa.Column(
            "billed_seconds_total",
            sa.Integer,
            nullable=False,
            server_default="0",
            comment="Mirror of instances.billed_seconds, maintained by the billing service",
        ),
    )

    # One active job per instance (stopped_at IS NULL rows are the active ones)
    op.create_index(
        "ix_billing_meter_jobs_instance",
        "billing_meter_jobs",
        ["instance_id"],
    )
    op.create_index(
        "ix_billing_meter_jobs_active",
        "billing_meter_jobs",
        ["instance_id", "stopped_at"],
    )
    # Unique active job: can't have two running meter jobs for the same instance
    op.create_index(
        "uq_billing_meter_jobs_active_instance",
        "billing_meter_jobs",
        ["instance_id"],
        unique=True,
        postgresql_where=sa.text("stopped_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_billing_meter_jobs_active_instance", table_name="billing_meter_jobs")
    op.drop_index("ix_billing_meter_jobs_active", table_name="billing_meter_jobs")
    op.drop_index("ix_billing_meter_jobs_instance", table_name="billing_meter_jobs")
    op.drop_table("billing_meter_jobs")
