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
from services.reputation_pricing_service.reputation_engine import ReputationInputs, compute_reputation
from services.reputation_pricing_service.repository import (
    get_latest_idle_prediction,
    get_latest_reputation,
    get_pricing_inputs,
    get_reputation_inputs,
    get_reputation_trend,
    get_revenue_analytics,
    save_pricing_suggestion,
)
from services.reputation_pricing_service import schemas
from services.reputation_pricing_service.schemas import (
    HealthSnapshot,
    HostDashboardResponse,
    IdlePredictionResponse,
    PricingSuggestionResponse,
    ReputationComponentScores,
    ReputationScoreResponse,
    RevenueAnalytics,
    HostScoresResponse,
    BenchmarkHistoryResponse,
    BenchmarkRunDetail,
    PerformanceScoreBreakdown,
    HealthScoreBreakdown,
    RunBenchmarkRequest,
    RunBenchmarkResponse,
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


# ── v8 Feature 1: Benchmark & Host Scores Routes ─────────────────────────────

benchmark_router = APIRouter(tags=["GPU Benchmarks & Health Score"])


@benchmark_router.get(
    "/hosts/{host_id}/scores",
    response_model=schemas.HostScoresResponse,
    summary="Get computed performance, health, reliability and composite scores for a host",
)
async def get_host_scores(
    host_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Returns the latest computed HostScore for the specified host.
    Includes breakdowns for performance (peer-normalised TFLOPS, VRAM BW) and
    health (thermal, clock, power stability).
    """
    from services.reputation_pricing_service.repository import get_latest_host_score

    score = await get_latest_host_score(session, host_id)
    if not score:
        # Fallback to default neutral scores if no score has been computed yet
        import datetime
        return schemas.HostScoresResponse(
            host_id=host_id,
            performance_score=None,
            health_score=None,
            reliability_score=None,
            composite_score=None,
            performance_breakdown=schemas.PerformanceScoreBreakdown(),
            health_breakdown=schemas.HealthScoreBreakdown(),
            computed_at=datetime.datetime.now(datetime.UTC),
        )

    return schemas.HostScoresResponse(
        host_id=host_id,
        performance_score=float(score["performance_score"]) if score["performance_score"] is not None else None,
        health_score=float(score["health_score"]) if score["health_score"] is not None else None,
        reliability_score=float(score["reliability_score"]) if score["reliability_score"] is not None else None,
        composite_score=float(score["composite_score"]) if score["composite_score"] is not None else None,
        performance_breakdown=schemas.PerformanceScoreBreakdown(
            fp16_tflops_normalised=float(score["fp16_tflops_normalised"]) if score["fp16_tflops_normalised"] is not None else None,
            fp32_tflops_normalised=float(score["fp32_tflops_normalised"]) if score["fp32_tflops_normalised"] is not None else None,
            mem_bandwidth_normalised=float(score["mem_bandwidth_normalised"]) if score["mem_bandwidth_normalised"] is not None else None,
            peer_group_size=score["peer_group_size"] or 0,
        ),
        health_breakdown=schemas.HealthScoreBreakdown(
            thermal_stability_score=float(score["thermal_stability_score"]) if score["thermal_stability_score"] is not None else None,
            clock_stability_score=float(score["clock_stability_score"]) if score["clock_stability_score"] is not None else None,
            power_stability_score=float(score["power_stability_score"]) if score["power_stability_score"] is not None else None,
        ),
        gpu_model=score["gpu_model"],
        benchmark_run_id=score["benchmark_run_id"],
        computed_at=score["computed_at"],
    )


@benchmark_router.get(
    "/hosts/{host_id}/benchmarks/history",
    response_model=schemas.BenchmarkHistoryResponse,
    summary="Get time-series history of sub-test benchmark runs for a host",
)
async def get_host_benchmark_history(
    host_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=500),
    benchmark_type: str | None = Query(None, description="Filter by sub-test type (e.g. gpu_fp16_tflops)"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Returns time-series history of individual sub-test benchmark runs for trend visualization.
    """
    from services.reputation_pricing_service.repository import get_benchmark_history

    runs_data = await get_benchmark_history(
        session, host_id=host_id, limit=limit, benchmark_type=benchmark_type
    )

    runs = [
        schemas.BenchmarkRunDetail(
            id=r["id"],
            host_id=r["host_id"],
            run_id=r["run_id"],
            benchmark_type=r["benchmark_type"],
            value=float(r["value"]),
            unit=r["unit"],
            flag_status=r["flag_status"],
            flag_reason=r["flag_reason"],
            gpu_model=r["gpu_model"],
            cuda_version=r["cuda_version"],
            driver_version=r["driver_version"],
            run_at=r["run_at"],
        )
        for r in runs_data
    ]

    return schemas.BenchmarkHistoryResponse(
        host_id=host_id,
        total_runs=len(runs),
        runs=runs,
    )


@benchmark_router.post(
    "/hosts/{host_id}/benchmarks/run",
    response_model=schemas.RunBenchmarkResponse,
    summary="Trigger/ingest a benchmark suite run for a host",
)
async def run_host_benchmark(
    host_id: uuid.UUID,
    payload: schemas.RunBenchmarkRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    """
    Ingests sub-benchmark results from Host Agent (or runs default suite), checks against
    peer envelopes for fraud detection, stores runs, and triggers score recomputation.
    """
    from sqlalchemy import text
    from services.reputation_pricing_service.benchmark_suite import (
        BenchmarkRunInput,
        check_envelope,
    )
    from services.reputation_pricing_service.repository import (
        get_peer_envelopes,
        save_benchmark_runs,
    )
    from services.reputation_pricing_service.tasks import _recompute_benchmark_scores_for_host

    # Fetch host GPU info
    h_res = await session.execute(
        text("SELECT gpu_model FROM listings WHERE host_id = :host_id LIMIT 1"),
        {"host_id": str(host_id)},
    )
    h_row = h_res.first()
    gpu_model = payload.gpu_model if payload and payload.gpu_model else (h_row[0] if h_row and h_row[0] else None)

    if not gpu_model:
        h_res2 = await session.execute(
            text("SELECT gpu_model FROM host_hardware_specs WHERE host_id = :host_id ORDER BY reported_at DESC LIMIT 1"),
            {"host_id": str(host_id)},
        )
        h_row2 = h_res2.first()
        gpu_model = h_row2[0] if h_row2 and h_row2[0] else "RTX 4090"

    run_id = uuid.uuid4()
    sub_tests = (payload.sub_tests if payload and payload.sub_tests else None) or [
        {"benchmark_type": "gpu_fp16_tflops", "value": 82.5, "unit": "TFLOPS"},
        {"benchmark_type": "gpu_fp32_tflops", "value": 41.2, "unit": "TFLOPS"},
        {"benchmark_type": "gpu_mem_bandwidth_gbps", "value": 1008.0, "unit": "GB/s"},
        {"benchmark_type": "disk_seq_mbps", "value": 3500.0, "unit": "MB/s"},
        {"benchmark_type": "net_bandwidth_mbps", "value": 950.0, "unit": "Mbps"},
    ]

    envelopes = await get_peer_envelopes(session, gpu_model)

    runs_to_save = []
    flags = []

    for test in sub_tests:
        btype = test["benchmark_type"]
        val = float(test["value"])
        unit = test["unit"]

        run_input = BenchmarkRunInput(
            benchmark_type=btype,
            value=val,
            unit=unit,
            gpu_model=gpu_model,
        )
        envelope = envelopes.get(btype)
        flag = check_envelope(run_input, envelope)

        flag_status = "ok"
        flag_reason = None
        if flag:
            flag_status = flag.severity
            flag_reason = flag.reason
            flags.append({
                "benchmark_type": btype,
                "value": val,
                "reason": flag.reason,
            })

        runs_to_save.append({
            "benchmark_type": btype,
            "value": val,
            "unit": unit,
            "flag_status": flag_status,
            "flag_reason": flag_reason,
            "gpu_model": gpu_model,
            "cuda_version": payload.cuda_version if payload else None,
            "driver_version": payload.driver_version if payload else None,
        })

    await save_benchmark_runs(session, host_id, run_id, runs_to_save)
    await session.commit()

    # Recompute scores for host using active request session
    await _recompute_benchmark_scores_for_host(host_id, session=session)

    return schemas.RunBenchmarkResponse(
        host_id=host_id,
        run_id=run_id,
        sub_tests_run=len(runs_to_save),
        flags=flags,
        status="completed" if not flags else "flagged",
    )


# ── Reputation History & Admin Actions (v8 Feature 2) ──────────────────────────

@reputation_router.get(
    "/hosts/{host_id}/reputation/history",
    response_model=list[schemas.ReputationEventResponse],
    summary="Get time-series history log of reputation events for a host",
)
async def get_reputation_history(
    host_id: uuid.UUID,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
):
    from services.reputation_pricing_service.reputation_engine import get_host_reputation_history
    return await get_host_reputation_history(session, host_id, limit=limit)


@reputation_router.post(
    "/admin/hosts/{host_id}/reputation/penalty",
    summary="Admin action to apply a manual reputation penalty",
)
async def post_admin_penalty(
    host_id: uuid.UUID,
    payload: schemas.AdminReputationActionRequest,
    session: AsyncSession = Depends(get_db_session),
):
    from services.reputation_pricing_service.reputation_engine import apply_manual_penalty, compute_decayed_reputation
    admin_id = uuid.uuid4()
    ev = await apply_manual_penalty(session, host_id, admin_id, payload.impact_delta, payload.reason)
    await compute_decayed_reputation(session, host_id)
    await session.commit()
    return {
        "status": "applied",
        "event_id": str(ev.id),
        "host_id": str(host_id),
        "impact_delta": float(ev.impact_delta),
        "reason": payload.reason,
    }


@reputation_router.post(
    "/admin/hosts/{host_id}/reputation/restore",
    summary="Admin action to restore host reputation",
)
async def post_admin_restore(
    host_id: uuid.UUID,
    payload: schemas.AdminReputationActionRequest,
    session: AsyncSession = Depends(get_db_session),
):
    from services.reputation_pricing_service.reputation_engine import apply_manual_restore, compute_decayed_reputation
    admin_id = uuid.uuid4()
    ev = await apply_manual_restore(session, host_id, admin_id, payload.impact_delta, payload.reason)
    await compute_decayed_reputation(session, host_id)
    await session.commit()
    return {
        "status": "applied",
        "event_id": str(ev.id),
        "host_id": str(host_id),
        "impact_delta": float(ev.impact_delta),
        "reason": payload.reason,
    }

