"""Phase 13 — Observability, Alerting & Incident Response

Revision ID: 0013_observability
Revises: 0012_infrastructure
Create Date: 2026-07-24

Schema additions for Phase 13:
  - alert_events: history log of all fired Prometheus/Alertmanager alerts
  - incident_records: operational incident tracking log with root cause & resolution
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = "0013_observability"
down_revision = "0012_infrastructure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── alert_events ─────────────────────────────────────────────────────────
    op.create_table(
        "alert_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("alert_name", sa.String(100), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False,
                  comment="critical | warning | info"),
        sa.Column("service_name", sa.String(100), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="firing",
                  comment="firing | resolved | suppressed"),
        sa.Column("labels", postgresql.JSONB, nullable=True),
        sa.Column("fired_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "idx_alert_events_name_status",
        "alert_events",
        ["alert_name", "status", "fired_at"]
    )
    op.create_index(
        "idx_alert_events_severity",
        "alert_events",
        ["severity"]
    )

    # ── incident_records ──────────────────────────────────────────────────────
    op.create_table(
        "incident_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False,
                  comment="SEV1 | SEV2 | SEV3 | SEV4"),
        sa.Column("status", sa.String(30), nullable=False, server_default="investigating",
                  comment="investigating | identified | monitoring | resolved"),
        sa.Column("lead_responder", sa.String(200), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("root_cause", sa.Text, nullable=True),
        sa.Column("resolution_notes", sa.Text, nullable=True),
        sa.Column("impact_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("impact_ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )

    op.create_index(
        "idx_incident_records_status_sev",
        "incident_records",
        ["status", "severity", "created_at"]
    )


def downgrade() -> None:
    op.drop_table("incident_records")
    op.drop_table("alert_events")
