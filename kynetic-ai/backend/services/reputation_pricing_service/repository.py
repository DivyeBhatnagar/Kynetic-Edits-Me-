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
                JOIN hosts h ON h.id = b.host_id
                WHERE h.gpu_model = (
                    SELECT gpu_model FROM hosts WHERE id = :host_id
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
