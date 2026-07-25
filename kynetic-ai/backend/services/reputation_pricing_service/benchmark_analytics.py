"""
Services/reputation_pricing_service/benchmark_analytics.py
v8 Feature 4 — GPU Benchmark Database & Analytics Engine.

Implements:
1. Refresh aggregation views/tables (refresh_gpu_benchmark_analytics)
2. List & detail summary analytics (get_gpu_model_summaries)
3. Side-by-side GPU comparison (compare_gpu_models)
4. Price/Performance ranking engine (get_price_performance_rankings)
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.marketplace_models import GpuModelStats, Listing, PricePerformanceStats, SearchableListing
from libs.db_models.reputation_pricing_models import HostBenchmarkRun, HostScore


async def refresh_gpu_benchmark_analytics(session: AsyncSession) -> dict[str, int]:
    """
    Refresh aggregate GPU performance and price/performance stats tables.
    """
    now = datetime.now(UTC)

    # 1. Aggregate sub-benchmark stats per GPU model from host_benchmark_runs
    stats_stmt = (
        select(
            HostBenchmarkRun.gpu_model,
            func.avg(
                case(
                    (HostBenchmarkRun.benchmark_type == "gpu_fp16_tflops", HostBenchmarkRun.value),
                    else_=None,
                )
            ).label("avg_fp16"),
            func.avg(
                case(
                    (HostBenchmarkRun.benchmark_type == "gpu_fp32_tflops", HostBenchmarkRun.value),
                    else_=None,
                )
            ).label("avg_fp32"),
            func.avg(
                case(
                    (HostBenchmarkRun.benchmark_type == "gpu_mem_bandwidth_gbps", HostBenchmarkRun.value),
                    else_=None,
                )
            ).label("avg_bw"),
            func.count(func.distinct(HostBenchmarkRun.host_id)).label("samples"),
        )
        .where(
            HostBenchmarkRun.gpu_model.isnot(None),
            HostBenchmarkRun.flag_status == "ok",
        )
        .group_by(HostBenchmarkRun.gpu_model)
    )

    stats_res = await session.execute(stats_stmt)
    rows = stats_res.all()

    # Clear old stats
    await session.execute(delete(GpuModelStats))

    stats_count = 0
    for r in rows:
        g_model = r[0]
        if not g_model:
            continue

        st_row = GpuModelStats(
            gpu_model=g_model,
            region="global",
            avg_tensor_fp16_tflops=float(r[1]) if r[1] is not None else None,
            avg_tensor_fp32_tflops=float(r[2]) if r[2] is not None else None,
            avg_mem_bandwidth_gbps=float(r[3]) if r[3] is not None else None,
            sample_count=int(r[4]),
            last_refreshed=now,
        )
        session.add(st_row)
        stats_count += 1

    # 2. Aggregate price/performance rankings from SearchableListing or Listing + HostScore
    pp_stmt = (
        select(
            Listing.gpu_model,
            func.avg(Listing.price_per_hour_usd).label("avg_price"),
            func.avg(HostScore.performance_score).label("avg_perf"),
        )
        .join(HostScore, Listing.host_id == HostScore.host_id)
        .where(
            Listing.gpu_model.isnot(None),
            HostScore.performance_score.isnot(None),
        )
        .group_by(Listing.gpu_model)
    )

    pp_res = await session.execute(pp_stmt)
    pp_rows = pp_res.all()

    await session.execute(delete(PricePerformanceStats))

    pp_count = 0
    for r in pp_rows:
        g_model = r[0]
        price_val = Decimal(str(r[1])) if r[1] is not None else Decimal("1.00")
        perf_val = float(r[2]) if r[2] is not None else 0.50
        ratio = perf_val / (float(price_val) + 0.001)

        pp_row = PricePerformanceStats(
            gpu_model=g_model,
            region="global",
            avg_price_per_hour_usd=price_val,
            avg_performance_score=perf_val,
            price_performance_ratio=round(ratio, 4),
            last_refreshed=now,
        )
        session.add(pp_row)
        pp_count += 1

    await session.flush()
    return {"gpu_model_stats": stats_count, "price_performance_stats": pp_count}


async def get_gpu_model_summaries(
    session: AsyncSession,
    model: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch list or detail summary analytics for tracked GPU models.
    """
    stmt = select(GpuModelStats)
    if model:
        stmt = stmt.where(func.lower(GpuModelStats.gpu_model) == func.lower(model))
    stmt = stmt.order_by(GpuModelStats.gpu_model.asc())

    res = await session.execute(stmt)
    rows = res.scalars().all()

    return [
        {
            "gpu_model": r.gpu_model,
            "region": r.region,
            "avg_tensor_fp16_tflops": float(r.avg_tensor_fp16_tflops) if r.avg_tensor_fp16_tflops is not None else None,
            "avg_tensor_fp32_tflops": float(r.avg_tensor_fp32_tflops) if r.avg_tensor_fp32_tflops is not None else None,
            "avg_mem_bandwidth_gbps": float(r.avg_mem_bandwidth_gbps) if r.avg_mem_bandwidth_gbps is not None else None,
            "sample_count": r.sample_count,
            "last_refreshed": r.last_refreshed.isoformat(),
        }
        for r in rows
    ]


async def compare_gpu_models(
    session: AsyncSession,
    model_a: str,
    model_b: str,
) -> dict[str, Any]:
    """
    Side-by-side comparison of two GPU models.
    """
    a_stats = await get_gpu_model_summaries(session, model=model_a)
    b_stats = await get_gpu_model_summaries(session, model=model_b)

    stat_a = a_stats[0] if a_stats else None
    stat_b = b_stats[0] if b_stats else None

    fp16_ratio = None
    if stat_a and stat_b and stat_a.get("avg_tensor_fp16_tflops") and stat_b.get("avg_tensor_fp16_tflops"):
        fp16_ratio = round(stat_a["avg_tensor_fp16_tflops"] / max(stat_b["avg_tensor_fp16_tflops"], 0.01), 2)

    return {
        "model_a": model_a,
        "model_b": model_b,
        "stats_a": stat_a,
        "stats_b": stat_b,
        "speedup_ratio_fp16": fp16_ratio,
        "recommendation": f"{model_a} provides {fp16_ratio}x FP16 throughput relative to {model_b}" if fp16_ratio else "Insufficient peer data for direct comparison",
    }


async def get_price_performance_rankings(
    session: AsyncSession,
    region: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """
    Fetch price/performance rankings sorted by score-per-dollar ratio descending.
    """
    stmt = select(PricePerformanceStats)
    if region:
        stmt = stmt.where(func.lower(PricePerformanceStats.region) == func.lower(region))
    stmt = stmt.order_by(PricePerformanceStats.price_performance_ratio.desc()).limit(limit)

    res = await session.execute(stmt)
    rows = res.scalars().all()

    return [
        {
            "gpu_model": r.gpu_model,
            "region": r.region,
            "avg_price_per_hour_usd": float(r.avg_price_per_hour_usd),
            "avg_performance_score": float(r.avg_performance_score),
            "price_performance_ratio": float(r.price_performance_ratio),
            "last_refreshed": r.last_refreshed.isoformat(),
        }
        for r in rows
    ]
