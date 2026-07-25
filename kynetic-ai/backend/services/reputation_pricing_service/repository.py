"""
reputation_pricing_service — Database repository.

All reads use raw SQL (no ORM object graph traversal) to avoid N+1 issues
across service boundaries.  Writes use the ORM for type safety.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.reputation_pricing_models import (
    IdlePrediction,
    PricingSuggestion,
    ReputationScore,
    HostBenchmarkRun,
    HostScore,
    GpuModelEnvelope,
)

log = structlog.get_logger(__name__)


# ── Reputation reads ──────────────────────────────────────────────────────────

async def get_latest_reputation(
    session: AsyncSession, host_id: uuid.UUID
) -> dict | None:
    """Fetch the most recent ReputationScore row for a host."""
    result = await session.execute(
        text("""
            SELECT
                id, host_id, uptime_score, latency_score, network_score,
                job_success_rate, benchmark_score_normalised, response_time_score,
                composite_score, jobs_evaluated, computed_at
            FROM reputation_scores
            WHERE host_id = :host_id
            ORDER BY computed_at DESC
            LIMIT 1
        """),
        {"host_id": str(host_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


async def get_reputation_trend(
    session: AsyncSession,
    host_id: uuid.UUID,
    limit: int = 7,
) -> list[float]:
    """Return the last `limit` composite scores for trend display."""
    result = await session.execute(
        text("""
            SELECT composite_score
            FROM reputation_scores
            WHERE host_id = :host_id
            ORDER BY computed_at DESC
            LIMIT :limit
        """),
        {"host_id": str(host_id), "limit": limit},
    )
    rows = result.fetchall()
    # Reverse so oldest-first for charting
    return [float(r[0]) for r in reversed(rows)]


async def get_reputation_inputs(
    session: AsyncSession,
    host_id: uuid.UUID,
    window_days: int = 30,
    expected_heartbeats_per_day: int = 1440,
) -> dict[str, Any]:
    """
    Aggregate raw telemetry inputs for reputation computation.

    Queries three tables:
      host_heartbeats  — uptime + health
      instances        — job outcomes
      host_benchmarks  — benchmark scores
    """
    since = datetime.now(UTC) - timedelta(days=window_days)

    # ── Uptime from heartbeats ────────────────────────────────────────────────
    hb_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS received,
                AVG(CASE WHEN status = 'active' THEN 1.0 ELSE 0.0 END) AS active_frac,
                AVG(NULLIF(network_throughput_mbps, 0)) AS avg_throughput_mbps,
                AVG(gpu_temperature_celsius) AS avg_gpu_temp,
                AVG(cpu_temperature_celsius) AS avg_cpu_temp,
                AVG(power_draw_watts) AS avg_power_draw,
                MAX(received_at) AS last_heartbeat_at
            FROM host_heartbeats
            WHERE host_id = :host_id
              AND received_at >= :since
        """),
        {"host_id": str(host_id), "since": since},
    )
    hb = dict(hb_result.mappings().first() or {})
    heartbeats_received = int(hb.get("received") or 0)
    heartbeats_expected = window_days * expected_heartbeats_per_day

    # ── Job outcomes from instances ───────────────────────────────────────────
    job_result = await session.execute(
        text("""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                AVG(EXTRACT(EPOCH FROM (updated_at - created_at)) * 1000)
                    FILTER (WHERE status = 'running') AS avg_provision_ms
            FROM instances
            WHERE host_id = :host_id
              AND created_at >= :since
        """),
        {"host_id": str(host_id), "since": since},
    )
    jobs = dict(job_result.mappings().first() or {})

    # ── Benchmark from host_benchmarks ────────────────────────────────────────
    bench_result = await session.execute(
        text("""
            SELECT score
            FROM host_benchmarks
            WHERE host_id = :host_id
            ORDER BY run_at DESC
            LIMIT 1
        """),
        {"host_id": str(host_id)},
    )
    bench_row = bench_result.first()
    benchmark_raw = float(bench_row[0]) if bench_row else None

    # GPU-class min/max for normalisation (peers with same gpu_model in benchmarks)
    if benchmark_raw is not None:
        peer_result = await session.execute(
            text("""
                SELECT MIN(b.score) AS min_score, MAX(b.score) AS max_score
                FROM host_benchmarks b
                JOIN listings l ON l.host_id = b.host_id
                WHERE l.gpu_model = (
                    SELECT gpu_model FROM listings WHERE host_id = :host_id LIMIT 1
                )
            """),
            {"host_id": str(host_id)},
        )
        peer = dict(peer_result.mappings().first() or {})
    else:
        peer = {"min_score": 0.0, "max_score": 1.0}

    return {
        "heartbeats_received": heartbeats_received,
        "heartbeats_expected": heartbeats_expected,
        "active_frac": float(hb.get("active_frac") or 0.0),
        "avg_throughput_mbps": hb.get("avg_throughput_mbps"),
        "avg_gpu_temp": hb.get("avg_gpu_temp"),
        "avg_cpu_temp": hb.get("avg_cpu_temp"),
        "avg_power_draw": hb.get("avg_power_draw"),
        "last_heartbeat_at": hb.get("last_heartbeat_at"),
        "jobs_total": int(jobs.get("total") or 0),
        "jobs_completed": int(jobs.get("completed") or 0),
        "avg_provision_latency_ms": jobs.get("avg_provision_ms"),
        "benchmark_raw": benchmark_raw,
        "benchmark_class_min": float(peer.get("min_score") or 0.0),
        "benchmark_class_max": float(peer.get("max_score") or 1.0),
    }


async def save_reputation_score(
    session: AsyncSession,
    host_id: uuid.UUID,
    result,           # ReputationResult from reputation.py
    jobs_evaluated: int,
) -> ReputationScore:
    """Insert a new reputation snapshot row (append-only)."""
    row = ReputationScore(
        host_id=host_id,
        uptime_score=result.uptime_score,
        latency_score=result.latency_score,
        network_score=result.network_score,
        job_success_rate=result.job_success_rate,
        benchmark_score_normalised=result.benchmark_score_normalised,
        response_time_score=result.response_time_score,
        composite_score=result.composite_score,
        jobs_evaluated=jobs_evaluated,
    )
    session.add(row)
    return row


# ── Pricing reads / writes ────────────────────────────────────────────────────

async def get_pricing_inputs(
    session: AsyncSession,
    gpu_model: str | None,
    region: str | None,
) -> dict[str, Any]:
    """
    Aggregate supply/demand signals for the pricing model.
    """
    # Current supply count (active listings for this GPU class + region)
    supply_result = await session.execute(
        text("""
            SELECT COUNT(*) AS supply_count
            FROM listings
            WHERE status = 'active'
              AND (:gpu_model IS NULL OR lower(gpu_model) LIKE lower(:gpu_pattern))
              AND (:region IS NULL OR region = :region)
        """),
        {
            "gpu_model": gpu_model,
            "gpu_pattern": f"%{gpu_model}%" if gpu_model else None,
            "region": region,
        },
    )
    supply_count = int((supply_result.scalar() or 0))

    # Recent demand count (provisioning requests in last 7 days)
    seven_days_ago = datetime.now(UTC) - timedelta(days=7)
    demand_result = await session.execute(
        text("""
            SELECT COUNT(*) AS demand_count
            FROM instances i
            JOIN listings l ON l.id = i.listing_id
            WHERE i.created_at >= :since
              AND (:gpu_model IS NULL OR lower(l.gpu_model) LIKE lower(:gpu_pattern))
              AND (:region IS NULL OR l.region = :region)
        """),
        {
            "gpu_model": gpu_model,
            "gpu_pattern": f"%{gpu_model}%" if gpu_model else None,
            "region": region,
            "since": seven_days_ago,
        },
    )
    demand_count = int((demand_result.scalar() or 0))

    # Training rows for model refresh (all active listings with benchmark scores)
    training_result = await session.execute(
        text("""
            SELECT
                l.gpu_model,
                l.gpu_vram_gb,
                l.gpu_count,
                l.region,
                l.price_per_hour_usd,
                b.score AS benchmark_score
            FROM listings l
            LEFT JOIN LATERAL (
                SELECT score FROM host_benchmarks
                WHERE host_id = l.host_id
                ORDER BY run_at DESC LIMIT 1
            ) b ON true
            WHERE l.status = 'active'
            LIMIT 5000
        """),
        {},
    )
    training_rows = [dict(r) for r in training_result.mappings()]

    return {
        "supply_count": supply_count,
        "demand_count": demand_count,
        "training_rows": training_rows,
    }


async def save_pricing_suggestion(
    session: AsyncSession,
    listing_id: uuid.UUID,
    suggested_usd: Decimal,
    suggested_inr: Decimal,
    ci_low: Decimal,
    ci_high: Decimal,
    model_version: str,
) -> PricingSuggestion:
    row = PricingSuggestion(
        listing_id=listing_id,
        suggested_price_usd=suggested_usd,
        suggested_price_inr=suggested_inr,
        model_version=model_version,
        confidence_interval_low_usd=ci_low,
        confidence_interval_high_usd=ci_high,
    )
    session.add(row)
    return row


# ── Idle prediction reads / writes ─────────────────────────────────────────────

async def get_heartbeats_for_host(
    session: AsyncSession, host_id: uuid.UUID, window_days: int = 30
) -> list[dict]:
    """Fetch heartbeat rows for idle prediction."""
    since = datetime.now(UTC) - timedelta(days=window_days)
    result = await session.execute(
        text("""
            SELECT status, received_at
            FROM host_heartbeats
            WHERE host_id = :host_id
              AND received_at >= :since
            ORDER BY received_at DESC
        """),
        {"host_id": str(host_id), "since": since},
    )
    return [dict(r) for r in result.mappings()]


async def save_idle_prediction(
    session: AsyncSession,
    host_id: uuid.UUID,
    prediction: dict,
) -> IdlePrediction:
    row = IdlePrediction(
        host_id=host_id,
        **prediction,
    )
    session.add(row)
    return row


async def get_latest_idle_prediction(
    session: AsyncSession, host_id: uuid.UUID
) -> dict | None:
    result = await session.execute(
        text("""
            SELECT *
            FROM idle_predictions
            WHERE host_id = :host_id
            ORDER BY computed_at DESC
            LIMIT 1
        """),
        {"host_id": str(host_id)},
    )
    row = result.mappings().first()
    return dict(row) if row else None


# ── Revenue analytics ─────────────────────────────────────────────────────────

async def get_revenue_analytics(
    session: AsyncSession, host_id: uuid.UUID
) -> dict[str, Any]:
    """
    Aggregate billed revenue from wallet_transactions for the last 7 and 30 days.
    Falls back to instance metering records if wallet table is unavailable.
    """
    now = datetime.now(UTC)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    result = await session.execute(
        text("""
            SELECT
                COALESCE(SUM(amount_usd) FILTER (WHERE created_at >= :seven), 0) AS rev_7d_usd,
                COALESCE(SUM(amount_usd) FILTER (WHERE created_at >= :thirty), 0) AS rev_30d_usd,
                COALESCE(SUM(amount_inr) FILTER (WHERE created_at >= :seven), 0) AS rev_7d_inr,
                COALESCE(SUM(amount_inr) FILTER (WHERE created_at >= :thirty), 0) AS rev_30d_inr,
                COUNT(*) FILTER (WHERE created_at >= :thirty) AS jobs_30d,
                AVG(EXTRACT(EPOCH FROM (completed_at - created_at)) / 3600.0)
                    FILTER (WHERE status = 'completed' AND created_at >= :thirty) AS avg_hours
            FROM instances
            WHERE host_id = :host_id
              AND status = 'completed'
        """),
        {
            "host_id": str(host_id),
            "seven": seven_days_ago,
            "thirty": thirty_days_ago,
        },
    )
    row = dict(result.mappings().first() or {})
    return {
        "total_revenue_usd_7d": Decimal(str(row.get("rev_7d_usd") or 0)),
        "total_revenue_usd_30d": Decimal(str(row.get("rev_30d_usd") or 0)),
        "total_revenue_inr_7d": Decimal(str(row.get("rev_7d_inr") or 0)),
        "total_revenue_inr_30d": Decimal(str(row.get("rev_30d_inr") or 0)),
        "total_jobs_completed": int(row.get("jobs_30d") or 0),
        "avg_job_duration_hours": float(row.get("avg_hours") or 0.0),
    }


# ── v8 Feature 1: Benchmark & Host Scores Repository ─────────────────────────

async def save_benchmark_runs(
    session: AsyncSession,
    host_id: uuid.UUID,
    run_id: uuid.UUID,
    runs_data: list[dict],
) -> list[HostBenchmarkRun]:
    """
    Save a batch of sub-test benchmark results sharing one run_id.
    """
    inserted = []
    for data in runs_data:
        row = HostBenchmarkRun(
            host_id=host_id,
            run_id=run_id,
            benchmark_type=data["benchmark_type"],
            value=Decimal(str(data["value"])),
            unit=data["unit"],
            flag_status=data.get("flag_status", "ok"),
            flag_reason=data.get("flag_reason"),
            gpu_model=data.get("gpu_model"),
            cuda_version=data.get("cuda_version"),
            driver_version=data.get("driver_version"),
        )
        session.add(row)
        inserted.append(row)
    return inserted


async def get_latest_benchmark_runs(
    session: AsyncSession,
    host_id: uuid.UUID,
) -> list[dict]:
    """
    Fetch all sub-test rows belonging to the most recent run_id for a host.
    """
    from sqlalchemy import select
    subq = (
        select(HostBenchmarkRun.run_id)
        .where(HostBenchmarkRun.host_id == host_id)
        .order_by(HostBenchmarkRun.run_at.desc())
        .limit(1)
        .scalar_subquery()
    )
    stmt = (
        select(HostBenchmarkRun)
        .where(
            HostBenchmarkRun.host_id == host_id,
            HostBenchmarkRun.run_id == subq,
        )
        .order_by(HostBenchmarkRun.benchmark_type.asc())
    )
    result = await session.execute(stmt)
    scalars = result.scalars().all()
    return [
        {
            "id": r.id,
            "host_id": r.host_id,
            "run_id": r.run_id,
            "benchmark_type": r.benchmark_type,
            "value": float(r.value),
            "unit": r.unit,
            "flag_status": r.flag_status,
            "flag_reason": r.flag_reason,
            "gpu_model": r.gpu_model,
            "cuda_version": r.cuda_version,
            "driver_version": r.driver_version,
            "run_at": r.run_at,
        }
        for r in scalars
    ]


async def get_benchmark_history(
    session: AsyncSession,
    host_id: uuid.UUID,
    limit: int = 50,
    benchmark_type: str | None = None,
) -> list[dict]:
    """
    Fetch time-series of benchmark runs for trend charts and history API.
    """
    from sqlalchemy import select
    stmt = select(HostBenchmarkRun).where(HostBenchmarkRun.host_id == host_id)
    if benchmark_type:
        stmt = stmt.where(HostBenchmarkRun.benchmark_type == benchmark_type)
    stmt = stmt.order_by(HostBenchmarkRun.run_at.desc()).limit(limit)

    result = await session.execute(stmt)
    scalars = result.scalars().all()
    return [
        {
            "id": r.id,
            "host_id": r.host_id,
            "run_id": r.run_id,
            "benchmark_type": r.benchmark_type,
            "value": float(r.value),
            "unit": r.unit,
            "flag_status": r.flag_status,
            "flag_reason": r.flag_reason,
            "gpu_model": r.gpu_model,
            "cuda_version": r.cuda_version,
            "driver_version": r.driver_version,
            "run_at": r.run_at,
        }
        for r in scalars
    ]


async def get_peer_envelopes(
    session: AsyncSession,
    gpu_model: str,
) -> dict[str, Any]:
    """
    Build peer envelopes for a GPU model.
    Combines admin-defined envelopes (gpu_model_envelopes) with actual fleet peer statistics.
    """
    from sqlalchemy import select, func
    from services.reputation_pricing_service.benchmark_suite import PeerEnvelope

    # 1. Admin envelopes
    admin_stmt = select(GpuModelEnvelope).where(func.lower(GpuModelEnvelope.gpu_model) == func.lower(gpu_model))
    admin_res = await session.execute(admin_stmt)
    admin_rows = admin_res.scalars().all()
    admin_envelopes = {
        r.benchmark_type: {
            "benchmark_type": r.benchmark_type,
            "min_value": float(r.min_value),
            "max_value": float(r.max_value),
            "unit": r.unit,
        }
        for r in admin_rows
    }

    # 2. Fleet statistics per metric for this GPU model
    stats_stmt = (
        select(
            HostBenchmarkRun.benchmark_type,
            func.min(HostBenchmarkRun.value).label("peer_min"),
            func.max(HostBenchmarkRun.value).label("peer_max"),
            func.count(func.distinct(HostBenchmarkRun.host_id)).label("peer_count"),
        )
        .where(
            func.lower(HostBenchmarkRun.gpu_model) == func.lower(gpu_model),
            HostBenchmarkRun.flag_status == "ok",
        )
        .group_by(HostBenchmarkRun.benchmark_type)
    )
    stats_res = await session.execute(stats_stmt)
    fleet_stats = {
        r[0]: {
            "benchmark_type": r[0],
            "peer_min": float(r[1]) if r[1] is not None else None,
            "peer_max": float(r[2]) if r[2] is not None else None,
            "peer_count": int(r[3]),
        }
        for r in stats_res.fetchall()
    }

    all_types = set(admin_envelopes.keys()) | set(fleet_stats.keys())
    envelopes: dict[str, PeerEnvelope] = {}

    for btype in all_types:
        admin = admin_envelopes.get(btype)
        fstat = fleet_stats.get(btype)

        min_val = float(admin["min_value"]) if admin else float(fstat["peer_min"]) if fstat else 0.0
        max_val = float(admin["max_value"]) if admin else float(fstat["peer_max"]) if fstat else 1.0
        unit = admin["unit"] if admin else "points"

        peer_min = float(fstat["peer_min"]) if fstat and fstat["peer_min"] is not None else None
        peer_max = float(fstat["peer_max"]) if fstat and fstat["peer_max"] is not None else None
        peer_count = int(fstat["peer_count"]) if fstat else 0

        envelopes[btype] = PeerEnvelope(
            gpu_model=gpu_model,
            benchmark_type=btype,
            min_value=min_val,
            max_value=max_val,
            unit=unit,
            peer_min=peer_min,
            peer_max=peer_max,
            peer_count=peer_count,
        )

    return envelopes


async def get_heartbeats_for_health(
    session: AsyncSession,
    host_id: uuid.UUID,
    window_days: int = 7,
) -> list[dict]:
    """
    Fetch rolling 7-day heartbeat samples for health score computation.
    """
    from sqlalchemy import select
    from libs.db_models.host_models import HostHeartbeat
    since = datetime.now(UTC) - timedelta(days=window_days)
    stmt = (
        select(HostHeartbeat)
        .where(
            HostHeartbeat.host_id == host_id,
            HostHeartbeat.recorded_at >= since,
        )
        .order_by(HostHeartbeat.recorded_at.desc())
    )
    result = await session.execute(stmt)
    scalars = result.scalars().all()
    return [
        {
            "temperature_c": r.temperature_c,
            "power_draw_w": r.power_draw_w,
            "recorded_at": r.recorded_at,
        }
        for r in scalars
    ]


async def save_host_score(
    session: AsyncSession,
    host_id: uuid.UUID,
    perf_res,
    health_res,
    reliability_score: float | None,
    composite_score: float | None,
    gpu_model: str | None = None,
    benchmark_run_id: uuid.UUID | None = None,
) -> HostScore:
    """
    Insert a new HostScore row.
    """
    row = HostScore(
        host_id=host_id,
        performance_score=Decimal(str(perf_res.performance_score)) if perf_res.performance_score is not None else None,
        health_score=Decimal(str(health_res.health_score)) if health_res.health_score is not None else None,
        reliability_score=Decimal(str(reliability_score)) if reliability_score is not None else None,
        composite_score=Decimal(str(composite_score)) if composite_score is not None else None,
        fp16_tflops_normalised=Decimal(str(perf_res.fp16_tflops_normalised)) if perf_res.fp16_tflops_normalised is not None else None,
        fp32_tflops_normalised=Decimal(str(perf_res.fp32_tflops_normalised)) if perf_res.fp32_tflops_normalised is not None else None,
        mem_bandwidth_normalised=Decimal(str(perf_res.mem_bandwidth_normalised)) if perf_res.mem_bandwidth_normalised is not None else None,
        peer_group_size=perf_res.peer_group_size,
        thermal_stability_score=Decimal(str(health_res.thermal_stability_score)) if health_res.thermal_stability_score is not None else None,
        clock_stability_score=Decimal(str(health_res.clock_stability_score)) if health_res.clock_stability_score is not None else None,
        power_stability_score=Decimal(str(health_res.power_stability_score)) if health_res.power_stability_score is not None else None,
        gpu_model=gpu_model,
        benchmark_run_id=benchmark_run_id,
    )
    session.add(row)
    return row


async def get_latest_host_score(
    session: AsyncSession,
    host_id: uuid.UUID,
) -> dict | None:
    """
    Fetch the most recent HostScore row for a host.
    """
    from sqlalchemy import select
    stmt = (
        select(HostScore)
        .where(HostScore.host_id == host_id)
        .order_by(HostScore.computed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    r = result.scalars().first()
    if not r:
        return None
    return {
        "id": r.id,
        "host_id": r.host_id,
        "performance_score": float(r.performance_score) if r.performance_score is not None else None,
        "health_score": float(r.health_score) if r.health_score is not None else None,
        "reliability_score": float(r.reliability_score) if r.reliability_score is not None else None,
        "composite_score": float(r.composite_score) if r.composite_score is not None else None,
        "fp16_tflops_normalised": float(r.fp16_tflops_normalised) if r.fp16_tflops_normalised is not None else None,
        "fp32_tflops_normalised": float(r.fp32_tflops_normalised) if r.fp32_tflops_normalised is not None else None,
        "mem_bandwidth_normalised": float(r.mem_bandwidth_normalised) if r.mem_bandwidth_normalised is not None else None,
        "peer_group_size": r.peer_group_size,
        "thermal_stability_score": float(r.thermal_stability_score) if r.thermal_stability_score is not None else None,
        "clock_stability_score": float(r.clock_stability_score) if r.clock_stability_score is not None else None,
        "power_stability_score": float(r.power_stability_score) if r.power_stability_score is not None else None,
        "gpu_model": r.gpu_model,
        "benchmark_run_id": r.benchmark_run_id,
        "computed_at": r.computed_at,
    }

