"""
Alembic migration — Phase 8: Host Experience, Auto-Pricing & Reputation Layer.

Creates:
  reputation_scores   — append-only per-host reputation snapshots (6 components + composite)
  pricing_suggestions — auto-pricing model outputs per listing
  idle_predictions    — per-host idle-time + income projection forecasts
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0008_reputation_pricing"
down_revision = "0007_router_copilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── reputation_scores ─────────────────────────────────────────────────────
    op.create_table(
        "reputation_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "host_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Component scores — all Numeric(4,3) so we can store 0.000–1.000
        sa.Column("uptime_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("latency_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("network_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("job_success_rate", sa.Numeric(4, 3), nullable=True),
        sa.Column("benchmark_score_normalised", sa.Numeric(4, 3), nullable=True),
        sa.Column("response_time_score", sa.Numeric(4, 3), nullable=True),
        # Weighted composite
        sa.Column("composite_score", sa.Numeric(4, 3), nullable=False),
        sa.Column("jobs_evaluated", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_reputation_scores_host_id", "reputation_scores", ["host_id"]
    )
    op.create_index(
        "ix_reputation_scores_host_computed",
        "reputation_scores",
        ["host_id", "computed_at"],
    )

    # ── pricing_suggestions ───────────────────────────────────────────────────
    op.create_table(
        "pricing_suggestions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "listing_id",
            UUID(as_uuid=True),
            sa.ForeignKey("listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("suggested_price_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("suggested_price_inr", sa.Numeric(12, 4), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("confidence_interval_low_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("confidence_interval_high_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("accepted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_pricing_suggestions_listing_id", "pricing_suggestions", ["listing_id"]
    )

    # ── idle_predictions ──────────────────────────────────────────────────────
    op.create_table(
        "idle_predictions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "host_id",
            UUID(as_uuid=True),
            sa.ForeignKey("hosts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("predicted_idle_hours_per_day", sa.Numeric(5, 2), nullable=False),
        sa.Column("predicted_utilization_fraction", sa.Numeric(4, 3), nullable=False),
        sa.Column("income_projection_monthly_usd", sa.Numeric(12, 4), nullable=False),
        sa.Column("income_projection_monthly_inr", sa.Numeric(14, 2), nullable=False),
        sa.Column("electricity_cost_monthly_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("net_income_monthly_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("price_per_hour_usd_used", sa.Numeric(12, 6), nullable=True),
        sa.Column("heartbeats_sampled", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_idle_predictions_host_id", "idle_predictions", ["host_id"]
    )
    op.create_index(
        "ix_idle_predictions_host_computed",
        "idle_predictions",
        ["host_id", "computed_at"],
    )


def downgrade() -> None:
    op.drop_table("idle_predictions")
    op.drop_table("pricing_suggestions")
    op.drop_table("reputation_scores")
