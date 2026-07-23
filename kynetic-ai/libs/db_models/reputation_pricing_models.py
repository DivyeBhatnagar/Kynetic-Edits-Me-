"""
Phase 8 DB Models: Host Experience, Auto-Pricing & Reputation Layer.

Tables:
  reputation_scores   — per-host composite + component scores, snapshot per computation
  pricing_suggestions — auto-pricing suggestions per listing (accepted or overridden)
  idle_predictions    — per-host idle-time + income projections
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from libs.db_models.database import Base


# ── ReputationScore ───────────────────────────────────────────────────────────

class ReputationScore(Base):
    """
    Immutable snapshot of a host's reputation at a point in time.

    Append-only: we never UPDATE a row — we INSERT a new snapshot after every
    completed job and on scheduled sweeps (Celery task).  Trend data is derived
    by querying the most-recent N rows.

    Score semantics: all component scores and the composite are in [0.0, 1.0].
    Security note (Pillar 6): scoring inputs are sourced exclusively from
    already-verified telemetry tables (host_heartbeats, host_benchmarks,
    instances) — no self-reported fields are used.
    """

    __tablename__ = "reputation_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Component scores ──────────────────────────────────────────────────────
    # All in [0.0, 1.0].  NULL means the input telemetry was absent for this window.

    uptime_score: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True,
        comment="Fraction of heartbeats received in the last 30d window"
    )
    latency_score: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True,
        comment="Normalised inverse of p99 provisioning latency"
    )
    network_score: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True,
        comment="Normalised network throughput / quality from job telemetry"
    )
    job_success_rate: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True,
        comment="Fraction of jobs that completed successfully (not failed/evicted)"
    )
    benchmark_score_normalised: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True,
        comment="Latest benchmark score normalised to [0,1] vs. GPU class peers"
    )
    response_time_score: Mapped[float | None] = mapped_column(
        Numeric(4, 3), nullable=True,
        comment="How quickly the host agent responds to provisioning requests"
    )

    # ── Composite ─────────────────────────────────────────────────────────────
    composite_score: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False,
        comment="Weighted composite of the six component scores"
    )

    # Snapshot metadata
    jobs_evaluated: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    __table_args__ = (
        # Efficient "latest score for host" query
        Index("ix_reputation_scores_host_computed", "host_id", "computed_at"),
    )


# ── PricingSuggestion ─────────────────────────────────────────────────────────

class PricingSuggestion(Base):
    """
    Auto-pricing suggestion for a listing, generated at creation/update time
    by the scikit-learn regression model.

    The host can accept the suggestion (accepted=True) or override it
    (accepted=False, their manual price is on the listing row itself).
    """

    __tablename__ = "pricing_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Suggested prices (never float — always Decimal to avoid rounding errors)
    suggested_price_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False
    )
    suggested_price_inr: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False
    )

    # Model metadata — stored for drift detection + explainability
    model_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence_interval_low_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    confidence_interval_high_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )

    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )


# ── IdlePrediction ────────────────────────────────────────────────────────────

class IdlePrediction(Base):
    """
    Per-host idle-time forecast and expected monthly income projection.

    Recomputed periodically by the `predict_idle_time` Celery task.
    We keep one row per (host_id, computed_at) so trend display is possible.
    """

    __tablename__ = "idle_predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Idle prediction
    predicted_idle_hours_per_day: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False,
        comment="Estimated hours per day the machine will be idle (0-24)"
    )
    predicted_utilization_fraction: Mapped[float] = mapped_column(
        Numeric(4, 3), nullable=False,
        comment="Fraction of time machine is rented out (0.0-1.0)"
    )

    # Income projection — derived from current price × predicted utilization × 30d
    income_projection_monthly_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False,
        comment="Expected monthly gross revenue in USD"
    )
    income_projection_monthly_inr: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False
    )

    # Electricity cost estimate (simple formula: power_w × util_hours × kwh_rate)
    electricity_cost_monthly_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True
    )
    net_income_monthly_usd: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 4), nullable=True,
        comment="income_projection - electricity_cost"
    )

    # Input features snapshot (for drift detection)
    price_per_hour_usd_used: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 6), nullable=True
    )
    heartbeats_sampled: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )

    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    __table_args__ = (
        Index("ix_idle_predictions_host_computed", "host_id", "computed_at"),
    )
