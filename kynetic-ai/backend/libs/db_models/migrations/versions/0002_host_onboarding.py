"""Phase 2 migration: hosts, host_hardware_specs, host_benchmarks, host_heartbeats

Revision ID: 0002_host_onboarding
Revises: 0001_initial_schema
Create Date: 2026-07-23 00:00:00.000000 UTC

Adds all tables for Phase 2 — Host Onboarding, Hardware Verification & Benchmarking.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_host_onboarding"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Enums ─────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE host_status AS ENUM (
            'pending_verification', 'benchmarking', 'verified',
            'listed', 'flagged', 'suspended'
        )
    """)
    op.execute("CREATE TYPE os_type AS ENUM ('windows', 'linux', 'macos')")
    op.execute("CREATE TYPE benchmark_type AS ENUM ('llm_inference', 'image_gen', 'flops')")
    op.execute("CREATE TYPE heartbeat_status AS ENUM ('idle', 'busy', 'offline')")
    op.execute("CREATE TYPE disk_type AS ENUM ('nvme', 'ssd', 'hdd', 'unknown')")

    # ── hosts ─────────────────────────────────────────────────────────────────
    op.create_table(
        "hosts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "pending_verification", "benchmarking", "verified",
                "listed", "flagged", "suspended",
                name="host_status", create_type=False
            ),
            nullable=False,
            server_default="pending_verification",
        ),
        sa.Column(
            "os_type",
            postgresql.ENUM("windows", "linux", "macos", name="os_type", create_type=False),
            nullable=False,
        ),
        sa.Column("agent_version", sa.String(50), nullable=False),
        sa.Column("mtls_cert_fingerprint", sa.String(64), nullable=True),
        sa.Column("spec_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("benchmark_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("flagged_reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_hosts_user_id", "hosts", ["user_id"])
    op.create_index("ix_hosts_status", "hosts", ["status"])
    op.create_index("ix_hosts_mtls_cert_fingerprint", "hosts", ["mtls_cert_fingerprint"], unique=True)

    # ── host_hardware_specs ───────────────────────────────────────────────────
    op.create_table(
        "host_hardware_specs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cpu_model", sa.String(255), nullable=True),
        sa.Column("cpu_cores", sa.Integer(), nullable=False),
        sa.Column("cpu_threads", sa.Integer(), nullable=False),
        sa.Column("ram_gb", sa.Float(), nullable=False),
        sa.Column(
            "disk_type",
            postgresql.ENUM("nvme", "ssd", "hdd", "unknown", name="disk_type", create_type=False),
            nullable=False,
            server_default="unknown",
        ),
        sa.Column("disk_gb", sa.Float(), nullable=False),
        sa.Column("gpu_model", sa.String(255), nullable=True),
        sa.Column("gpu_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gpu_vram_gb", sa.Float(), nullable=True),
        sa.Column("driver_version", sa.String(50), nullable=True),
        sa.Column("cuda_version", sa.String(20), nullable=True),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("power_draw_w", sa.Float(), nullable=True),
        sa.Column("raw_spec", postgresql.JSONB(), nullable=True),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_host_hardware_specs_host_id", "host_hardware_specs", ["host_id"])
    op.create_index(
        "ix_host_hardware_specs_host_reported",
        "host_hardware_specs", ["host_id", "reported_at"]
    )

    # ── host_benchmarks ───────────────────────────────────────────────────────
    op.create_table(
        "host_benchmarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "benchmark_type",
            postgresql.ENUM(
                "llm_inference", "image_gen", "flops",
                name="benchmark_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("raw_metrics", postgresql.JSONB(), nullable=True),
        sa.Column("is_rerun", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_host_benchmarks_host_id", "host_benchmarks", ["host_id"])
    op.create_index("ix_host_benchmarks_run_at", "host_benchmarks", ["run_at"])
    op.create_index(
        "ix_host_benchmarks_host_type", "host_benchmarks", ["host_id", "benchmark_type"]
    )
    op.create_index(
        "ix_host_benchmarks_type_score", "host_benchmarks", ["benchmark_type", "score"]
    )

    # ── host_heartbeats ───────────────────────────────────────────────────────
    # High-volume time-series — partitioned by month in production.
    # In this migration we create a plain table; partitioning is a prod-infra concern.
    op.create_table(
        "host_heartbeats",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "host_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("idle", "busy", "offline", name="heartbeat_status", create_type=False),
            nullable=False,
        ),
        sa.Column("temperature_c", sa.Float(), nullable=True),
        sa.Column("power_draw_w", sa.Float(), nullable=True),
        sa.Column("gpu_utilization_pct", sa.Float(), nullable=True),
        sa.Column("ram_used_gb", sa.Float(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_host_heartbeats_host_id", "host_heartbeats", ["host_id"])
    op.create_index("ix_host_heartbeats_recorded_at", "host_heartbeats", ["recorded_at"])
    op.create_index(
        "ix_host_heartbeats_host_recorded", "host_heartbeats", ["host_id", "recorded_at"]
    )


def downgrade() -> None:
    op.drop_table("host_heartbeats")
    op.drop_table("host_benchmarks")
    op.drop_table("host_hardware_specs")
    op.drop_table("hosts")

    op.execute("DROP TYPE IF EXISTS heartbeat_status")
    op.execute("DROP TYPE IF EXISTS benchmark_type")
    op.execute("DROP TYPE IF EXISTS disk_type")
    op.execute("DROP TYPE IF EXISTS os_type")
    op.execute("DROP TYPE IF EXISTS host_status")
