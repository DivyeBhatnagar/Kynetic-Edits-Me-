"""
Alembic migration — Phase 5: Security Hardening tables.

Creates:
  device_fingerprints
  trust_tiers
  security_event_logs
  kill_switch_events

Plus ENUM types for each.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0005_security"
down_revision = "0004_provisioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    trust_tier_level = sa.Enum(
        "unverified", "tier1", "tier2", "tier3",
        name="trust_tier_level"
    )
    security_event_type = sa.Enum(
        "login_success", "login_failure", "signup",
        "device_fingerprint_new", "device_fingerprint_match",
        "multi_account_suspected", "crypto_mining_detected",
        "image_scan_passed", "image_scan_failed",
        "wallet_fraud_suspected", "kill_switch_triggered",
        "trust_tier_change", "rate_limit_exceeded", "abuse_blocked",
        name="security_event_type"
    )
    security_event_severity = sa.Enum(
        "info", "warning", "critical",
        name="security_event_severity"
    )
    kill_switch_target_type = sa.Enum(
        "instance", "host", "account",
        name="kill_switch_target_type"
    )
    trust_tier_level.create(op.get_bind(), checkfirst=True)
    security_event_type.create(op.get_bind(), checkfirst=True)
    security_event_severity.create(op.get_bind(), checkfirst=True)
    kill_switch_target_type.create(op.get_bind(), checkfirst=True)

    # ── device_fingerprints ───────────────────────────────────────────────────
    op.create_table(
        "device_fingerprints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fingerprint_hash", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.Text),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("seen_count", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint("user_id", "fingerprint_hash", name="uq_device_fp_user_hash"),
    )
    op.create_index("ix_device_fp_user_id", "device_fingerprints", ["user_id"])
    op.create_index("ix_device_fp_hash", "device_fingerprints", ["fingerprint_hash"])

    # ── trust_tiers ───────────────────────────────────────────────────────────
    op.create_table(
        "trust_tiers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tier", trust_tier_level, nullable=False, server_default="unverified"),
        sa.Column("max_instance_vcpus", sa.Integer, server_default="2"),
        sa.Column("max_gpu_vram_gb", sa.Integer),
        sa.Column("max_gpu_hours_month", sa.Integer, server_default="10"),
        sa.Column("max_spend_usd_month", sa.Numeric(precision=12, scale=2), server_default="50.00"),
        sa.Column("is_wallet_frozen", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", name="uq_trust_tier_user"),
    )
    op.create_index("ix_trust_tiers_user_id", "trust_tiers", ["user_id"])

    # ── security_event_logs ───────────────────────────────────────────────────
    op.create_table(
        "security_event_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", security_event_type, nullable=False),
        sa.Column("severity", security_event_severity, nullable=False, server_default="info"),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", sa.String(36)),
        sa.Column("user_id", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("details", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_sec_events_type", "security_event_logs", ["event_type"])
    op.create_index("ix_sec_events_resource", "security_event_logs", ["resource_id"])
    op.create_index("ix_sec_events_user", "security_event_logs", ["user_id"])
    op.create_index("ix_sec_events_created", "security_event_logs", ["created_at"])

    # ── kill_switch_events ────────────────────────────────────────────────────
    op.create_table(
        "kill_switch_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("target_type", kill_switch_target_type, nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("triggered_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reason", sa.Text),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("broadcast_result", JSONB),
    )
    op.create_index("ix_kill_switch_target", "kill_switch_events", ["target_id"])


def downgrade() -> None:
    op.drop_table("kill_switch_events")
    op.drop_table("security_event_logs")
    op.drop_table("trust_tiers")
    op.drop_table("device_fingerprints")
    for enum_name in [
        "kill_switch_target_type", "security_event_severity",
        "security_event_type", "trust_tier_level"
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
