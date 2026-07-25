"""
Phase 29 — DB Migration: host_commands

Adds table `host_commands` for audit logging of signed, idempotent control-plane
commands sent to Host Agents (launch, stop, terminate).

Migration ID: 0013_host_commands
Depends on: 0012_billing_meter_jobs
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "host_commands",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "command_type",
            sa.Enum("launch", "stop", "terminate", name="command_type_enum"),
            nullable=False,
        ),
        sa.Column(
            "idempotency_key",
            sa.String(100),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "status",
            sa.Enum("sent", "acked", "failed", "timed_out", name="command_status_enum"),
            nullable=False,
            server_default="sent",
        ),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("acked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index("ix_host_commands_host_id", "host_commands", ["host_id"])
    op.create_index("ix_host_commands_instance_id", "host_commands", ["instance_id"])
    op.create_index("ix_host_commands_idempotency", "host_commands", ["idempotency_key"])
    op.create_index(
        "ix_host_commands_host_instance", "host_commands", ["host_id", "instance_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_host_commands_host_instance", table_name="host_commands")
    op.drop_index("ix_host_commands_idempotency", table_name="host_commands")
    op.drop_index("ix_host_commands_instance_id", table_name="host_commands")
    op.drop_index("ix_host_commands_host_id", table_name="host_commands")
    op.drop_table("host_commands")
    op.execute("DROP TYPE IF EXISTS command_status_enum")
    op.execute("DROP TYPE IF EXISTS command_type_enum")
