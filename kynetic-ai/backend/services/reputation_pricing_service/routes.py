"""
reputation_pricing_service — API routes.

Endpoints:
  GET /hosts/{host_id}/reputation    — reputation score + components + trend
  GET /hosts/{host_id}/dashboard     — full host dashboard
  GET /pricing/suggest               — auto-pricing suggestion for a listing
"""

import uuid
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.common.auth import require_auth
from services.reputation_pricing_service.config import get_settings
from services.reputation_pricing_service.pricing import predict_idle_time
from services.reputation_pricing_service.pricing import PricingFeatures, suggest_price
from services.reputation_pricing_service.reputation import ReputationInputs, compute_reputation
from services.reputation_pricing_service.repository import (
    get_latest_idle_prediction,
    get_latest_reputation,
    get_pricing_inputs,
    get_reputation_inputs,
    get_reputation_trend,
    get_revenue_analytics,
    save_pricing_suggestion,
)
from services.reputation_pricing_service.schemas import (
    HealthSnapshot,
    HostDashboardResponse,
    IdlePredictionResponse,
    PricingSuggestionResponse,
    ReputationComponentScores,
    ReputationScoreResponse,
    RevenueAnalytics,
)

log = structlog.get_logger(__name__)
settings = get_settings()

reputation_router = APIRouter(tags=["Reputation"])
dashboard_router = APIRouter(tags=["Host Dashboard"])
pricing_router = APIRouter(tags=["Auto-Pricing"])


# ── GET /hosts/{host_id}/reputation ──────────────────────────────────────────

@reputation_router.get(
    "/hosts/{host_id}/reputation",
    response_model=ReputationScoreResponse,
    summary="Get reputation score and sub-components for a host",
)
async def get_host_reputation(
    host_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Returns the most recent reputation snapshot for the host.

    The score is computed by the `recompute_reputation` Celery task after every
    completed job and on the hourly sweep.  If no reputation data exists yet,
    returns a neutral score of 0.5 with all components NULL.
    """
    row = await get_latest_reputation(session, host_id)
    trend = await get_reputation_trend(session, host_id, limit=7)

    if row is None:
        # Host exists but has no scored history yet
        return ReputationScoreResponse(
            host_id=host_id,
            composite_score=0.5,
            components=ReputationComponentScores(),
            jobs_evaluated=0,
            computed_at=__import__("datetime").datetime.utcnow(),
            trend=[],
        )

    return ReputationScoreResponse(
        host_id=host_id,
        composite_score=float(row["composite_score"]),
        components=ReputationComponentScores(
            uptime_score=float(row["uptime_score"]) if row["uptime_score"] is not None else None,
            latency_score=float(row["latency_score"]) if row["latency_score"] is not None else None,
            network_score=float(row["network_score"]) if row["network_score"] is not None else None,
            job_success_rate=float(row["job_success_rate"]) if row["job_success_rate"] is not None else None,
            benchmark_score_normalised=float(row["benchmark_score_normalised"]) if row["benchmark_score_normalised"] is not None else None,
            response_time_score=float(row["response_time_score"]) if row["response_time_score"] is not None else None,
        ),
        jobs_evaluated=int(row["jobs_evaluated"]),
        computed_at=row["computed_at"],
        trend=trend,
    )


# ── GET /hosts/{host_id}/dashboard ────────────────────────────────────────────

@dashboard_router.get(
    "/hosts/{host_id}/dashboard",
    response_model=HostDashboardResponse,
    summary="Full host dashboard: revenue, health, pricing suggestion, reputation",
)
async def get_host_dashboard(
    host_id: uuid.UUID,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Aggregates all Phase 8 data for the host dashboard:
      - Revenue analytics (7d + 30d)
      - Health snapshot (latest heartbeat + hardware telemetry)
      - Reputation score + trend
      - Idle prediction + income projection
      - Pricing suggestion (for the host's most recent active listing)
    """
    owner_id = uuid.UUID(auth["sub"])
    # TODO: verify host ownership (cross-service call to host_service)
    # For now we trust the JWT sub matches host owner — gated by auth middleware.

    import asyncio
    reputation_row, trend, revenue, idle_row = await asyncio.gather(
        get_latest_reputation(session, host_id),
        get_reputation_trend(session, host_id),
        get_revenue_analytics(session, host_id),
        get_latest_idle_prediction(session, host_id),
    )

    # ── Health snapshot from latest heartbeat ─────────────────────────────────
    rep_inputs_raw = await get_reputation_inputs(
        session, host_id,
        window_days=settings.uptime_window_days,
        expected_heartbeats_per_day=settings.expected_heartbeats_per_day,
    )
    health = HealthSnapshot(
        last_heartbeat_at=rep_inputs_raw.get("last_heartbeat_at"),
        uptime_pct_30d=(
            round(rep_inputs_raw["active_frac"] * 100, 2)
            if rep_inputs_raw.get("active_frac") is not None else None
        ),
        gpu_temp_celsius=rep_inputs_raw.get("avg_gpu_temp"),
        cpu_temp_celsius=rep_inputs_raw.get("avg_cpu_temp"),
        power_draw_watts=rep_inputs_raw.get("avg_power_draw"),
    )

    # ── Compose reputation response ───────────────────────────────────────────
    if reputation_row:
        reputation_resp = ReputationScoreResponse(
            host_id=host_id,
            composite_score=float(reputation_row["composite_score"]),
            components=ReputationComponentScores(
                uptime_score=float(reputation_row["uptime_score"]) if reputation_row["uptime_score"] is not None else None,
                latency_score=float(reputation_row["latency_score"]) if reputation_row["latency_score"] is not None else None,
                network_score=float(reputation_row["network_score"]) if reputation_row["network_score"] is not None else None,
                job_success_rate=float(reputation_row["job_success_rate"]) if reputation_row["job_success_rate"] is not None else None,
                benchmark_score_normalised=float(reputation_row["benchmark_score_normalised"]) if reputation_row["benchmark_score_normalised"] is not None else None,
                response_time_score=float(reputation_row["response_time_score"]) if reputation_row["response_time_score"] is not None else None,
            ),
            jobs_evaluated=int(reputation_row["jobs_evaluated"]),
            computed_at=reputation_row["computed_at"],
            trend=trend,
        )
    else:
        reputation_resp = None

    # ── Idle prediction ────────────────────────────────────────────────────────
    idle_resp: IdlePredictionResponse | None = None
    if idle_row:
        idle_resp = IdlePredictionResponse(
            host_id=host_id,
            **{k: idle_row[k] for k in IdlePredictionResponse.model_fields if k in idle_row and k != "host_id"},
            computed_at=idle_row["computed_at"],
        )

    return HostDashboardResponse(
        host_id=host_id,
        reputation=reputation_resp,
        revenue=RevenueAnalytics(**revenue),
        health=health,
        idle_prediction=idle_resp,
        pricing_suggestion=None,  # Fetched on-demand via /pricing/suggest
    )


# ── GET /pricing/suggest ──────────────────────────────────────────────────────

@pricing_router.get(
    "/pricing/suggest",
    response_model=PricingSuggestionResponse,
    summary="Get auto-pricing suggestion for a listing",
)
async def get_pricing_suggestion(
    listing_id: uuid.UUID = Query(..., description="The listing to suggest a price for"),
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Returns a competitive price suggestion from the auto-pricing model.

    The host can accept or override the suggestion.  The suggestion is also
    persisted to `pricing_suggestions` for model feedback.
    """
    # Fetch listing metadata for feature engineering
    from sqlalchemy import text
    listing_result = await session.execute(
        text("""
            SELECT id, gpu_model, gpu_vram_gb, gpu_count, region, host_id
            FROM listings
            WHERE id = :listing_id
        """),
        {"listing_id": str(listing_id)},
    )
    listing = listing_result.mappings().first()
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    pricing_inputs = await get_pricing_inputs(
        session,
        gpu_model=listing["gpu_model"],
        region=listing["region"],
    )

    # Benchmark score for this host
    bench_result = await session.execute(
        text("""
            SELECT score FROM host_benchmarks
            WHERE host_id = :host_id
            ORDER BY run_at DESC LIMIT 1
        """),
        {"host_id": str(listing["host_id"])},
    )
    bench_row = bench_result.first()
    benchmark_score = float(bench_row[0]) if bench_row else None

    features = PricingFeatures(
        gpu_model=listing["gpu_model"],
        benchmark_score=benchmark_score,
        region=listing["region"],
        gpu_vram_gb=listing["gpu_vram_gb"],
        gpu_count=listing["gpu_count"],
        current_supply_count=pricing_inputs["supply_count"],
        recent_demand_count=pricing_inputs["demand_count"],
    )

    sug_usd, sug_inr, ci_low, ci_high, version, rationale = suggest_price(
        features,
        floor_usd=settings.pricing_floor_usd,
        cap_usd=settings.pricing_cap_usd,
        usd_to_inr_rate=settings.usd_to_inr_rate,
    )

    # Persist suggestion for model feedback loop
    suggestion = await save_pricing_suggestion(
        session, listing_id, sug_usd, sug_inr, ci_low, ci_high, version
    )
    await session.commit()

    return PricingSuggestionResponse(
        listing_id=listing_id,
        suggested_price_usd=sug_usd,
        suggested_price_inr=sug_inr,
        confidence_interval_low_usd=ci_low,
        confidence_interval_high_usd=ci_high,
        model_version=version,
        rationale=rationale,
    )
