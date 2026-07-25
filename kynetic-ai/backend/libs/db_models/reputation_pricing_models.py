"""
Phase 8 DB Models: Host Experience, Auto-Pricing & Reputation Layer.
v8 Extension: GPU Benchmark & Health Score (Feature 1).

Tables:
  reputation_scores     — per-host composite + component scores, snapshot per computation
  pricing_suggestions   — auto-pricing suggestions per listing (accepted or overridden)
  idle_predictions      — per-host idle-time + income projections
  host_benchmark_runs   — [v8] individual sub-test results (GPU/CPU/RAM/disk/net), one row per run×type
  host_scores           — [v8] computed performance/health/reliability/composite scores per host
  gpu_model_envelopes   — [v8] admin-maintained min/max ranges per (gpu_model, metric) for fraud detection
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
    Text,
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

    # ── Additional v8 snapshot analytics ─────────────────────────────────────
    completed_jobs: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    cancelled_jobs: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    failed_jobs: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    dispute_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    refund_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    policy_violation_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    decay_factor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("1.0000"))
    last_decayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Efficient "latest score for host" query
        Index("ix_reputation_scores_host_computed", "host_id", "computed_at"),
    )


# ── ReputationEvent ───────────────────────────────────────────────────────────

class ReputationEvent(Base):
    """
    Append-only event log of events affecting a host's reputation score.
    v8 Feature 2 — Host Reputation System.
    """

    __tablename__ = "reputation_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
        comment="job_completed, job_cancelled, job_failed, dispute_opened, refund_issued, violation_flagged, manual_penalty, manual_restore"
    )
    impact_delta: Mapped[Decimal] = mapped_column(
        Numeric(8, 4), nullable=False, default=Decimal("0.0000"),
        comment="Raw reputation impact adjustment"
    )
    metadata_json: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="JSON payload describing event context"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    __table_args__ = (
        Index("ix_reputation_events_host_created", "host_id", "created_at"),
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


# ── HostBenchmarkRun (v8 Feature 1) ──────────────────────────────────────────

class HostBenchmarkRun(Base):
    """
    v8 Feature 1: Individual sub-benchmark result for a host.

    One row per (host_id, run_id, benchmark_type).  A single scheduled benchmark
    suite produces multiple rows sharing the same `run_id`.  Kept separate from
    the legacy `host_benchmarks` composite row so trend queries never need JSONB
    unpacking.

    Flag states:
      ok        — within the expected GPU-model envelope (fraud-safe)
      flagged   — outside envelope, pending admin re-verification
      skipped   — sub-test could not run on this host (e.g., no NVMe disk)

    Security: results are only accepted over the authenticated Gateway mTLS
    control stream; unsigned or mismatched results are rejected upstream before
    this row is written.
    """

    __tablename__ = "host_benchmark_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Groups all sub-tests belonging to a single benchmark suite invocation
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True, default=uuid.uuid4
    )
    # Sub-test identifier:
    #   gpu_fp16_tflops | gpu_fp32_tflops | gpu_mem_bandwidth_gbps | gpu_pcie_bandwidth_gbps
    #   cpu_score | ram_bandwidth_gbps | disk_seq_mbps | disk_rand_iops | net_bandwidth_mbps
    benchmark_type: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[float] = mapped_column(
        Numeric(16, 4), nullable=False,
        comment="Raw measured value for this sub-test"
    )
    unit: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment="e.g. TFLOPS, GB/s, IOPS, Mbps, points"
    )
    flag_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ok",
        comment="ok | flagged | skipped"
    )
    flag_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Human-readable reason for flagged status"
    )
    # GPU context captured at benchmark time
    gpu_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cuda_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    driver_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    __table_args__ = (
        # Efficient trend queries: host × type × time
        Index("ix_hbr_host_type_run_at", "host_id", "benchmark_type", "run_at"),
        # Efficient per-run-id retrieval (all sub-tests in one suite invocation)
        Index("ix_hbr_run_id", "run_id"),
    )


# ── HostScore (v8 Feature 1) ──────────────────────────────────────────────────

class HostScore(Base):
    """
    v8 Feature 1: Computed performance / health / reliability / composite
    scores for a host, recomputed after every benchmark run and on schedule.

    Replaces / supersedes the single `composite_score` previously embedded
    directly in `reputation_scores`.  Going forward, `ReputationScore.benchmark_
    score_normalised` is sourced from this table's `performance_score` field.

    Append-only: never UPDATE, always INSERT a new row.  "Latest" is always
    MAX(computed_at) for the host.
    """

    __tablename__ = "host_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Primary scores ────────────────────────────────────────────────────────
    # All in [0.0, 1.0]; NULL = insufficient data.

    performance_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True,
        comment="Peer-group-normalised GPU throughput + memory bandwidth (FP16/FP32)"
    )
    health_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True,
        comment="Rolling 7-day thermal/clock-stability/power score from heartbeat data"
    )
    reliability_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True,
        comment="Job completion rate + uptime fraction — feeds reputation §2 directly"
    )
    composite_score: Mapped[float | None] = mapped_column(
        Numeric(5, 4), nullable=True,
        comment="Weighted mean of performance, health, reliability"
    )

    # ── Breakdown / explainability ────────────────────────────────────────────
    fp16_tflops_normalised: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    fp32_tflops_normalised: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    mem_bandwidth_normalised: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    peer_group_size: Mapped[int | None] = mapped_column(SmallInteger, nullable=True,
        comment="How many same-model hosts are in the peer group used for normalisation")

    # Thermal/stability breakdown from health computation
    thermal_stability_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    clock_stability_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    power_stability_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)

    # Snapshot metadata
    gpu_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    benchmark_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        comment="The run_id that triggered this recompute"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        index=True,
    )

    __table_args__ = (
        Index("ix_host_scores_host_computed", "host_id", "computed_at"),
    )


# ── GpuModelEnvelope (v8 Feature 1) ──────────────────────────────────────────

class GpuModelEnvelope(Base):
    """
    v8 Feature 1: Admin-maintained expected-performance envelopes per GPU model
    and benchmark metric.  Used by the fraud/flagging system (§1.11, §1.13) to
    detect spoofed or manipulated benchmark results.

    A benchmark result whose `value` falls outside [min_value, max_value] for
    its (gpu_model, benchmark_type) is automatically flagged.

    Rows are created/updated by admins via the internal admin dashboard.
    Never editable by hosts.
    """

    __tablename__ = "gpu_model_envelopes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False
    )
    # e.g. "RTX 4090", "A100", "H100 SXM5"
    gpu_model: Mapped[str] = mapped_column(String(128), nullable=False)
    # e.g. "gpu_fp16_tflops", "gpu_mem_bandwidth_gbps"
    benchmark_type: Mapped[str] = mapped_column(String(64), nullable=False)

    min_value: Mapped[float] = mapped_column(
        Numeric(16, 4), nullable=False,
        comment="Minimum expected value for a legitimate result from this GPU model"
    )
    max_value: Mapped[float] = mapped_column(
        Numeric(16, 4), nullable=False,
        comment="Maximum expected value; above this may indicate spoofed hardware"
    )
    unit: Mapped[str] = mapped_column(String(32), nullable=False)

    # Optional soft bounds for reporting (inside these = green, outside = amber, outside hard bounds = red)
    soft_min: Mapped[float | None] = mapped_column(Numeric(16, 4), nullable=True)
    soft_max: Mapped[float | None] = mapped_column(Numeric(16, 4), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        # Efficient single-row lookup per (model, type) pair
        Index("ix_gpu_envelope_model_type", "gpu_model", "benchmark_type", unique=True),
    )
