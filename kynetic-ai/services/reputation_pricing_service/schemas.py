"""
reputation_pricing_service — Pydantic schemas.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ── Reputation ─────────────────────────────────────────────────────────────────

class ReputationComponentScores(BaseModel):
    """The six component scores that make up a host's reputation."""
    uptime_score: float | None = Field(None, ge=0.0, le=1.0)
    latency_score: float | None = Field(None, ge=0.0, le=1.0)
    network_score: float | None = Field(None, ge=0.0, le=1.0)
    job_success_rate: float | None = Field(None, ge=0.0, le=1.0)
    benchmark_score_normalised: float | None = Field(None, ge=0.0, le=1.0)
    response_time_score: float | None = Field(None, ge=0.0, le=1.0)


class ReputationScoreResponse(BaseModel):
    """Response for GET /hosts/{id}/reputation."""
    host_id: uuid.UUID
    composite_score: float
    components: ReputationComponentScores
    jobs_evaluated: int
    computed_at: datetime
    # Trend: last 7 snapshots composite scores (oldest first)
    trend: list[float] = []

    class Config:
        from_attributes = True


# ── Pricing Suggestion ─────────────────────────────────────────────────────────

class PricingSuggestionResponse(BaseModel):
    """Response for GET /pricing/suggest."""
    listing_id: uuid.UUID
    suggested_price_usd: Decimal
    suggested_price_inr: Decimal
    confidence_interval_low_usd: Decimal | None = None
    confidence_interval_high_usd: Decimal | None = None
    model_version: str
    # Human-readable rationale
    rationale: str

    class Config:
        from_attributes = True


# ── Idle Prediction / Dashboard ────────────────────────────────────────────────

class IdlePredictionResponse(BaseModel):
    """Idle time forecast for one host."""
    host_id: uuid.UUID
    predicted_idle_hours_per_day: float
    predicted_utilization_fraction: float
    income_projection_monthly_usd: Decimal
    income_projection_monthly_inr: Decimal
    electricity_cost_monthly_usd: Decimal | None = None
    net_income_monthly_usd: Decimal | None = None
    computed_at: datetime

    class Config:
        from_attributes = True


class RevenueAnalytics(BaseModel):
    """Revenue rollup for host dashboard."""
    total_revenue_usd_7d: Decimal
    total_revenue_usd_30d: Decimal
    total_revenue_inr_7d: Decimal
    total_revenue_inr_30d: Decimal
    total_jobs_completed: int
    avg_job_duration_hours: float


class HealthSnapshot(BaseModel):
    """Latest health/temperature telemetry from heartbeats."""
    last_heartbeat_at: datetime | None
    uptime_pct_30d: float | None
    gpu_temp_celsius: float | None
    cpu_temp_celsius: float | None
    power_draw_watts: float | None


class HostDashboardResponse(BaseModel):
    """Full host dashboard — GET /hosts/{id}/dashboard."""
    host_id: uuid.UUID
    reputation: ReputationScoreResponse | None
    revenue: RevenueAnalytics
    health: HealthSnapshot
    idle_prediction: IdlePredictionResponse | None
    pricing_suggestion: PricingSuggestionResponse | None
