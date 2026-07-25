"""
Alembic migration: 0004_provisioning

Creates:
  Enums:  instance_status_enum
  Tables: instances, ssh_sessions, secure_deletion_receipts
  Indexes: partial index on running instances, composite indexes

Depends on: 0003_marketplace_wallet (listings, wallets tables)

upgrade:  create enum → create tables → create indexes
downgrade: drop tables → drop enum (reverse order)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "0004"
down_revision: str = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enum ──────────────────────────────────────────────────────────────────
    instance_status = postgresql.ENUM(
        "pending",
        "provisioning",
        "running",
        "stopping",
        "stopped",
        "terminated",
        "failed",
        name="instance_status_enum",
    )
    instance_status.create(op.get_bind(), checkfirst=True)

    # ── instances ─────────────────────────────────────────────────────────────
    op.create_table(
        "instances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "developer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "provisioning", "running", "stopping",
                "stopped", "terminated", "failed",
                name="instance_status_enum",
                create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("hold_amount", sa.Numeric(16, 6), nullable=False),
        sa.Column("hold_released", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("firecracker_vm_id", sa.String(100)),
        sa.Column("container_id", sa.String(100)),
        sa.Column("agent_host_url", sa.String(500)),
        sa.Column("wireguard_ip", sa.String(20)),
        sa.Column("public_ip", sa.String(50)),
        sa.Column("ssh_port", sa.Integer, nullable=False, server_default="22"),
        sa.Column("billed_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("price_per_second_usd", sa.Numeric(20, 10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("stopped_at", sa.DateTime(timezone=True)),
        sa.Column("terminated_at", sa.DateTime(timezone=True)),
        # Constraints
        sa.CheckConstraint("billed_seconds >= 0", name="ck_instances_billed_seconds_nonneg"),
        sa.CheckConstraint("hold_amount >= 0", name="ck_instances_hold_amount_nonneg"),
    )
    op.create_index("ix_instances_developer_id", "instances", ["developer_id"])
    op.create_index("ix_instances_listing_id", "instances", ["listing_id"])
    op.create_index("ix_instances_host_id", "instances", ["host_id"])
    op.create_index("ix_instances_status", "instances", ["status"])
    op.create_index(
        "ix_instances_developer_status",
        "instances",
        ["developer_id", "status"],
    )
    op.create_index(
        "ix_instances_host_status",
        "instances",
        ["host_id", "status"],
    )
    # Partial index: only running instances (billing watcher hot path)
    op.execute(
        "CREATE INDEX ix_instances_running ON instances (id) "
        "WHERE status = 'running'"
    )

    # ── ssh_sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "ssh_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("public_key", sa.Text, nullable=False),
        sa.Column("private_key_encrypted", sa.Text),  # NULL after termination
        sa.Column("relay_host", sa.String(255)),
        sa.Column("relay_port", sa.Integer),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_ssh_sessions_instance_id", "ssh_sessions", ["instance_id"])

    # ── secure_deletion_receipts ──────────────────────────────────────────────
    op.create_table(
        "secure_deletion_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "instance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instances.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column("method", sa.String(100), nullable=False),
        sa.Column("agent_confirmation_hash", sa.String(128), nullable=False),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("agent_payload", sa.Text),
    )
    op.create_index(
        "ix_secure_deletion_instance_id",
        "secure_deletion_receipts",
        ["instance_id"],
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("secure_deletion_receipts")
    op.drop_table("ssh_sessions")
    op.drop_table("instances")

    op.execute("DROP TYPE IF EXISTS instance_status_enum")
