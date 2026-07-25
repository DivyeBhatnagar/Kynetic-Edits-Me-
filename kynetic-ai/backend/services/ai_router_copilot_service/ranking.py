"""
AI Router — Weighted Scoring / Ranking Function.

Implements the rule-based MVP ranking as specified in the Phase 7 plan:
  "rule-based, evolving to ML-based as job outcome data accumulates."

Algorithm
─────────
For each active listing, compute three normalised sub-scores (0.0–1.0):

  1. price_score      — inverse of price (cheaper = higher score)
  2. benchmark_score  — normalised hardware performance from host_benchmarks
  3. availability_score — binary (host online/available = 1.0, else penalised)
  4. reputation_score   — Phase 8 live score (or 0.5 neutral fallback)

Composite score = w_price × price_score
               + w_benchmark × benchmark_score
               + w_availability × availability_score
               + w_reputation × reputation_score   ← Phase 8 live

Weights are configurable via RouterCopilotSettings and default to:
  price=0.35, benchmark=0.30, availability=0.20, reputation=0.15

Phase 8 Integration
───────────────────
rank_listings() now accepts a `reputation_scores` dict (host_id → float) that
is fetched from reputation_pricing_service by the caller (router_routes.py).
If the dict is absent or a host has no score, we fall back to 0.5 (neutral),
so the ranking degrades gracefully for new hosts.
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import structlog

from services.ai_router_copilot_service.schemas import ScoredListing

log = structlog.get_logger(__name__)


# ── Reference workload for cost/time estimation ───────────────────────────────
# "How long would a standard fine-tuning job take on this machine?"
# Rough linear model: reference_flops / machine_tflops = hours
# Adjust REFERENCE_FLOPS to match the target workload for your MVP.
REFERENCE_FLOPS = 1e14   # ~100 TFLOPs — typical LoRA fine-tune pass on a 7B model
FALLBACK_TFLOPS = 5.0    # assumed TFLOPS for machines with no benchmark data


def _safe_float(v: Any, fallback: float = 0.0) -> float:
    """Coerce a potentially None / Decimal / str value to float."""
    if v is None:
        return fallback
    try:
        return float(v)
    except (TypeError, ValueError):
        return fallback


def _price_score(price_usd: float, min_price: float, max_price: float) -> float:
    """
    Normalise price to 0–1 where 1 = cheapest.

    Uses min–max inversion: score = 1 - (price - min) / (max - min + ε)
    """
    if max_price <= min_price:
        return 1.0  # only one price point — everyone gets full score
    return 1.0 - (price_usd - min_price) / (max_price - min_price + 1e-9)


def _benchmark_score_normalised(
    listing_benchmark: float | None,
    min_bench: float,
    max_bench: float,
) -> float:
    """
    Normalise benchmark to 0–1 where 1 = best performer.
    Missing benchmark → 0.3 (below average penalty, not zero so it's not excluded).
    """
    if listing_benchmark is None:
        return 0.3
    if max_bench <= min_bench:
        return 1.0
    return (listing_benchmark - min_bench) / (max_bench - min_bench + 1e-9)


def _availability_score(is_available: bool) -> float:
    """Binary: online and no active instance = 1.0, else 0.0."""
    return 1.0 if is_available else 0.0


def _estimated_cost_and_time(
    price_per_hour_usd: float,
    price_per_hour_inr: float,
    benchmark_score: float | None,
    goal: str | None,
    budget_usd: float | None,
) -> tuple[Decimal | None, Decimal | None, float | None]:
    """
    Estimate cost and time for a reference workload.

    Returns (estimated_cost_usd, estimated_cost_inr, estimated_hours).
    """
    tflops = _safe_float(benchmark_score, FALLBACK_TFLOPS)
    if tflops <= 0:
        tflops = FALLBACK_TFLOPS

    # Estimated hours based on reference workload
    estimated_hours = REFERENCE_FLOPS / (tflops * 1e12 * 3600)

    cost_usd = round(price_per_hour_usd * estimated_hours, 4)
    cost_inr = round(price_per_hour_inr * estimated_hours, 4)

    return Decimal(str(cost_usd)), Decimal(str(cost_inr)), round(estimated_hours, 3)


def rank_listings(
    listings: list[dict[str, Any]],
    *,
    goal: str | None = None,
    budget_usd: float | None = None,
    budget_inr: float | None = None,
    weight_price: float = 0.35,
    weight_benchmark: float = 0.30,
    weight_availability: float = 0.20,
    weight_reputation: float = 0.15,   # Phase 8 — live
    reputation_scores: dict[str, float] | None = None,  # host_id -> composite_score
    top_n: int = 10,
) -> list[ScoredListing]:
    """
    Rank a list of listing dicts and return the top-N ScoredListing objects.

    Parameters
    ──────────
    listings          : raw listing dicts from DB query
    goal              : 'fastest' | 'cheapest' | 'balanced' | None
    budget_usd        : hard budget ceiling in USD (optional)
    budget_inr        : hard budget ceiling in INR (optional)
    weight_*          : configurable scoring weights (must sum to 1.0)
    reputation_scores : Phase 8 — dict mapping host_id (str) → composite_score.
                        Fetched from reputation_pricing_service by router_routes.py.
                        Falls back to 0.5 (neutral) when absent.
    top_n             : maximum number of results to return

    Goal overrides weights (four-component, Phase 8)
    ─────────────────────────────────────────────────
    - 'fastest'  → benchmark=0.55, price=0.15, availability=0.15, reputation=0.15
    - 'cheapest' → price=0.65, benchmark=0.10, availability=0.15, reputation=0.10
    - 'balanced' → default weights
    """
    if goal == "fastest":
        weight_price, weight_benchmark, weight_availability, weight_reputation = 0.15, 0.55, 0.15, 0.15
    elif goal == "cheapest":
        weight_price, weight_benchmark, weight_availability, weight_reputation = 0.65, 0.10, 0.15, 0.10

    if not listings:
        return []

    # ── Budget filter ────────────────────────────────────────────────────────
    filtered = []
    for lst in listings:
        price_usd = _safe_float(lst.get("price_per_hour_usd"), 0.0)
        price_inr = _safe_float(lst.get("price_per_hour_inr"), 0.0)
        if budget_usd is not None and price_usd > budget_usd:
            continue
        if budget_inr is not None and price_inr > budget_inr:
            continue
        filtered.append(lst)

    if not filtered:
        log.warning("ranking.no_listings_after_budget_filter", total=len(listings))
        return []

    # ── Normalisation ranges ─────────────────────────────────────────────────
    prices = [_safe_float(l.get("price_per_hour_usd"), 0.0) for l in filtered]
    benchmarks = [
        _safe_float(l.get("benchmark_score"), None) or 0.0
        for l in filtered
    ]
    min_price, max_price = min(prices), max(prices)
    min_bench, max_bench = min(benchmarks), max(benchmarks)

    # ── Score each listing ───────────────────────────────────────────────────
    scored: list[tuple[float, ScoredListing]] = []
    for lst in filtered:
        price_usd = _safe_float(lst.get("price_per_hour_usd"), 0.0)
        price_inr = _safe_float(lst.get("price_per_hour_inr"), 0.0)
        bench_raw = lst.get("benchmark_score")
        bench_float = _safe_float(bench_raw, None) if bench_raw is not None else None
        is_available = bool(lst.get("is_available", True))

        sp = round(_price_score(price_usd, min_price, max_price), 4)
        sb = round(_benchmark_score_normalised(bench_float, min_bench, max_bench), 4)
        sa = round(_availability_score(is_available), 4)

        # Phase 8: live reputation score (falls back to 0.5 neutral for new hosts)
        host_id_str = str(lst.get("host_id", ""))
        rep_score = round(
            (reputation_scores or {}).get(host_id_str, 0.5), 4
        )

        composite = round(
            weight_price * sp
            + weight_benchmark * sb
            + weight_availability * sa
            + weight_reputation * rep_score,
            4,
        )

        est_cost_usd, est_cost_inr, est_hours = _estimated_cost_and_time(
            price_usd, price_inr, bench_float, goal, budget_usd
        )

        sl = ScoredListing(
            listing_id=lst["id"],
            host_id=lst["host_id"],
            title=lst.get("title"),
            gpu_model=lst.get("gpu_model"),
            gpu_count=lst.get("gpu_count"),
            gpu_vram_gb=_safe_float(lst.get("gpu_vram_gb"), None) or None,
            cpu_cores=lst.get("cpu_cores"),
            ram_gb=_safe_float(lst.get("ram_gb"), None) or None,
            region=lst.get("region"),
            price_per_hour_usd=Decimal(str(price_usd)),
            price_per_hour_inr=Decimal(str(price_inr)),
            estimated_cost_usd=est_cost_usd,
            estimated_cost_inr=est_cost_inr,
            estimated_hours=est_hours,
            score_price=sp,
            score_benchmark=sb,
            score_availability=sa,
            score_composite=composite,
            benchmark_score=bench_float,
            benchmark_type=lst.get("benchmark_type"),
            reputation_score=rep_score,  # Phase 8: live score
        )
        scored.append((composite, sl))

    scored.sort(key=lambda x: x[0], reverse=True)

    results = [sl for _, sl in scored[:top_n]]
    log.info(
        "ranking.complete",
        total_candidates=len(filtered),
        returned=len(results),
        goal=goal,
        budget_usd=budget_usd,
    )
    return results
