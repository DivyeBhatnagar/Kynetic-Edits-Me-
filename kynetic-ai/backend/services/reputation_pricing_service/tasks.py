"""
reputation_pricing_service — Celery tasks.

Tasks:
  recompute_reputation(host_id)        — recompute for a single host (triggered on job completion)
  recompute_reputation_sweep()         — batch sweep, called by Beat hourly
  train_or_refresh_pricing_model()     — retrain the Ridge regression model
  predict_idle_time_batch()            — compute idle predictions for all active hosts
"""

from __future__ import annotations

import asyncio
import uuid

import structlog

from services.reputation_pricing_service.celery_app import celery_app
from services.reputation_pricing_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


def _run_async(coro):
    """Run an async coroutine from a synchronous Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _recompute_for_host(host_id: uuid.UUID) -> float:
    """Core async logic for computing and persisting reputation for one host."""
    from libs.db_models.database import AsyncSessionFactory
    from services.reputation_pricing_service.reputation import ReputationInputs, compute_reputation
    from services.reputation_pricing_service.repository import (
        get_reputation_inputs,
        save_reputation_score,
    )

    async with AsyncSessionFactory() as session:
        raw = await get_reputation_inputs(
            session,
            host_id=host_id,
            window_days=settings.uptime_window_days,
            expected_heartbeats_per_day=settings.expected_heartbeats_per_day,
        )

        inputs = ReputationInputs(
            heartbeats_received=raw["heartbeats_received"],
            heartbeats_expected=raw["heartbeats_expected"],
            provisioning_latency_p99_ms=raw.get("avg_provision_latency_ms"),
            network_throughput_mbps=raw.get("avg_throughput_mbps"),
            jobs_completed=raw["jobs_completed"],
            jobs_total=raw["jobs_total"],
            benchmark_raw=raw.get("benchmark_raw"),
            benchmark_class_min=raw["benchmark_class_min"],
            benchmark_class_max=raw["benchmark_class_max"],
            avg_agent_response_ms=None,  # Phase 9: wired from provisioning telemetry
        )

        weights = {
            "uptime": settings.weight_uptime,
            "latency": settings.weight_latency,
            "network": settings.weight_network,
            "job_success": settings.weight_job_success,
            "benchmark": settings.weight_benchmark,
            "response_time": settings.weight_response_time,
        }

        result = compute_reputation(inputs, weights=weights)
        await save_reputation_score(session, host_id, result, jobs_evaluated=raw["jobs_total"])
        await session.commit()

        log.info(
            "reputation.recomputed",
            host_id=str(host_id),
            composite=round(result.composite_score, 4),
            jobs=raw["jobs_total"],
        )
        return result.composite_score


@celery_app.task(
    name="services.reputation_pricing_service.tasks.recompute_reputation",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def recompute_reputation(self, host_id: str) -> float:
    """
    Triggered by provisioning_service after a job completes.
    Also called by the hourly sweep for hosts with recent activity.
    """
    try:
        score = _run_async(_recompute_for_host(uuid.UUID(host_id)))
        return score
    except Exception as exc:
        log.error("reputation.task_failed", host_id=host_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.reputation_pricing_service.tasks.recompute_reputation_sweep",
    bind=True,
)
def recompute_reputation_sweep(self) -> dict:
    """
    Hourly batch: recompute reputation for all hosts with job activity
    in the last 24 hours.
    """

    async def _sweep():
        from sqlalchemy import text
        from libs.db_models.database import AsyncSessionFactory
        from datetime import datetime, timedelta, UTC

        async with AsyncSessionFactory() as session:
            result = await session.execute(
                text("""
                    SELECT DISTINCT host_id
                    FROM instances
                    WHERE updated_at >= :since
                """),
                {"since": datetime.now(UTC) - timedelta(hours=24)},
            )
            host_ids = [row[0] for row in result.fetchall()]

        scores = []
        for hid in host_ids:
            score = await _recompute_for_host(hid)
            scores.append(score)

        return {"hosts_processed": len(host_ids), "avg_composite": sum(scores) / len(scores) if scores else 0.0}

    return _run_async(_sweep())


@celery_app.task(
    name="services.reputation_pricing_service.tasks.train_or_refresh_pricing_model",
    bind=True,
)
def train_or_refresh_pricing_model(self) -> str:
    """
    Daily retrain of the Ridge regression pricing model.
    Fetches training rows from the marketplace DB and calls model.train().
    """

    async def _train():
        from libs.db_models.database import AsyncSessionFactory
        from services.reputation_pricing_service.repository import get_pricing_inputs
        from services.reputation_pricing_service.pricing import get_pricing_model

        async with AsyncSessionFactory() as session:
            pricing_data = await get_pricing_inputs(session, gpu_model=None, region=None)

        rows = pricing_data["training_rows"]
        model = get_pricing_model()
        version = model.train(rows)
        log.info("pricing_model.retrained", version=version, rows=len(rows))
        return version

    return _run_async(_train())


@celery_app.task(
    name="services.reputation_pricing_service.tasks.predict_idle_time_batch",
    bind=True,
)
def predict_idle_time_batch(self) -> dict:
    """
    6-hourly: compute idle predictions for all active hosts.
    """

    async def _batch():
        from sqlalchemy import text
        from libs.db_models.database import AsyncSessionFactory
        from services.reputation_pricing_service.repository import (
            get_heartbeats_for_host,
            save_idle_prediction,
        )
        from services.reputation_pricing_service.pricing import predict_idle_time

        async with AsyncSessionFactory() as session:
            result = await session.execute(
                text("""
                    SELECT DISTINCT h.id, l.price_per_hour_usd, hs.power_draw_watts
                    FROM hosts h
                    JOIN listings l ON l.host_id = h.id AND l.status = 'active'
                    LEFT JOIN hardware_specs hs ON hs.host_id = h.id
                    WHERE h.status = 'verified'
                """),
            )
            rows = result.fetchall()

        count = 0
        async with AsyncSessionFactory() as session:
            for host_id, price_usd, power_w in rows:
                heartbeats = await get_heartbeats_for_host(session, host_id)
                prediction = predict_idle_time(
                    heartbeats=heartbeats,
                    current_price_usd=price_usd,
                    usd_to_inr_rate=settings.usd_to_inr_rate,
                    electricity_kwh_rate_usd=settings.electricity_kwh_rate_usd,
                    power_draw_watts=float(power_w) if power_w else None,
                )
                await save_idle_prediction(session, host_id, prediction)
                count += 1
            await session.commit()

        log.info("idle_prediction.batch_done", hosts=count)
        return {"hosts_processed": count}

    return _run_async(_batch())


# ── v8 Feature 1: Benchmark & Host Scores Tasks ──────────────────────────────

async def _recompute_benchmark_scores_for_host(
    host_id: uuid.UUID,
    session: AsyncSession | None = None,
) -> dict:
    """
    Core async logic for recomputing HostScores (performance, health, reliability, composite).
    """
    from sqlalchemy import text
    from services.reputation_pricing_service.benchmark_suite import (
        BenchmarkRunInput,
        HeartbeatSample,
        compute_host_composite,
        compute_health_score,
        compute_performance_score,
    )
    from services.reputation_pricing_service.repository import (
        get_heartbeats_for_health,
        get_latest_benchmark_runs,
        get_latest_reputation,
        get_peer_envelopes,
        save_host_score,
    )

    async def _compute_on_session(sess: AsyncSession) -> dict:
        # 1. Fetch host's GPU model from listings or host_hardware_specs
        h_res = await sess.execute(
            text("SELECT gpu_model FROM listings WHERE host_id = :host_id LIMIT 1"),
            {"host_id": str(host_id)},
        )
        h_row = h_res.first()
        gpu_model = h_row[0] if h_row and h_row[0] else None

        if not gpu_model:
            h_res2 = await sess.execute(
                text("SELECT gpu_model FROM host_hardware_specs WHERE host_id = :host_id ORDER BY reported_at DESC LIMIT 1"),
                {"host_id": str(host_id)},
            )
            h_row2 = h_res2.first()
            gpu_model = h_row2[0] if h_row2 and h_row2[0] else "RTX 4090"

        # 2. Latest benchmark runs
        raw_runs = await get_latest_benchmark_runs(sess, host_id)
        run_inputs = [
            BenchmarkRunInput(
                benchmark_type=r["benchmark_type"],
                value=float(r["value"]),
                unit=r["unit"],
                gpu_model=r.get("gpu_model") or gpu_model,
                cuda_version=r.get("cuda_version"),
                driver_version=r.get("driver_version"),
            )
            for r in raw_runs
        ]
        run_id = raw_runs[0]["run_id"] if raw_runs else None

        # 3. Peer envelopes for GPU model
        envelopes = await get_peer_envelopes(sess, gpu_model)

        # 4. Performance score
        perf_res = compute_performance_score(run_inputs, envelopes)

        # 5. Health score from rolling trailing 7-day heartbeats
        hb_rows = await get_heartbeats_for_health(sess, host_id, window_days=7)
        hb_samples = [
            HeartbeatSample(
                gpu_temperature_celsius=float(r["temperature_c"]) if r["temperature_c"] is not None else None,
                power_draw_watts=float(r["power_draw_w"]) if r["power_draw_w"] is not None else None,
            )
            for r in hb_rows
        ]
        health_res = compute_health_score(hb_samples)

        # 6. Reliability score from latest reputation composite
        latest_rep = await get_latest_reputation(sess, host_id)
        reliability_score = float(latest_rep["composite_score"]) if latest_rep else None

        # 7. Overall HostScore composite
        composite = compute_host_composite(
            perf_res.performance_score,
            health_res.health_score,
            reliability_score,
        )

        # 8. Save HostScore
        await save_host_score(
            sess,
            host_id,
            perf_res,
            health_res,
            reliability_score,
            composite,
            gpu_model=gpu_model,
            benchmark_run_id=run_id,
        )

        log.info(
            "host_scores.recomputed",
            host_id=str(host_id),
            perf=perf_res.performance_score,
            health=health_res.health_score,
            reliability=reliability_score,
            composite=composite,
        )

        return {
            "host_id": str(host_id),
            "performance_score": perf_res.performance_score,
            "health_score": health_res.health_score,
            "reliability_score": reliability_score,
            "composite_score": composite,
        }

    if session is not None:
        return await _compute_on_session(session)

    from libs.db_models.database import AsyncSessionFactory
    async with AsyncSessionFactory() as new_session:
        res = await _compute_on_session(new_session)
        await new_session.commit()
        return res


@celery_app.task(
    name="services.reputation_pricing_service.tasks.recompute_benchmark_scores",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def recompute_benchmark_scores(self, host_id: str) -> dict:
    """
    Triggered after a new benchmark suite finishes on a host agent.
    """
    try:
        return _run_async(_recompute_benchmark_scores_for_host(uuid.UUID(host_id)))
    except Exception as exc:
        log.error("benchmark_scores.task_failed", host_id=host_id, error=str(exc))
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.reputation_pricing_service.tasks.benchmark_sweep",
    bind=True,
)
def benchmark_sweep(self) -> dict:
    """
    Daily Celery Beat task: recompute HostScores for all hosts with benchmark history.
    """
    async def _sweep():
        from sqlalchemy import text
        from libs.db_models.database import AsyncSessionFactory

        async with AsyncSessionFactory() as session:
            result = await session.execute(
                text("SELECT DISTINCT host_id FROM host_benchmark_runs")
            )
            host_ids = [row[0] for row in result.fetchall()]

        processed = 0
        for hid in host_ids:
            await _recompute_benchmark_scores_for_host(hid)
            processed += 1

        log.info("benchmark_sweep.completed", hosts=processed)
        return {"hosts_processed": processed}

    return _run_async(_sweep())

