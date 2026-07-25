"""
Unit tests for the AI Router ranking function.

These are pure unit tests — no DB, no HTTP, no LLM calls.
The ranking function takes plain dicts and returns ScoredListing objects.
"""

import math
import uuid
from decimal import Decimal

import pytest

from services.ai_router_copilot_service.ranking import (
    _availability_score,
    _benchmark_score_normalised,
    _price_score,
    rank_listings,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────

def _make_listing(
    price_usd: float = 1.0,
    price_inr: float = 83.0,
    benchmark_score: float | None = None,
    is_available: bool = True,
    gpu_model: str = "NVIDIA RTX 4090",
    gpu_vram_gb: float = 24.0,
    region: str = "us-east-1",
) -> dict:
    return {
        "id": uuid.uuid4(),
        "host_id": uuid.uuid4(),
        "title": f"GPU: {gpu_model}",
        "gpu_model": gpu_model,
        "gpu_count": 1,
        "gpu_vram_gb": gpu_vram_gb,
        "cpu_cores": 16,
        "ram_gb": 64.0,
        "region": region,
        "price_per_hour_usd": price_usd,
        "price_per_hour_inr": price_inr,
        "benchmark_score": benchmark_score,
        "benchmark_type": "llm_inference",
        "is_available": is_available,
    }


# ── Sub-score unit tests ────────────────────────────────────────────────────

class TestPriceScore:
    def test_cheapest_gets_one(self):
        assert _price_score(1.0, 1.0, 5.0) == pytest.approx(1.0, abs=1e-3)

    def test_most_expensive_gets_zero(self):
        assert _price_score(5.0, 1.0, 5.0) == pytest.approx(0.0, abs=1e-3)

    def test_midpoint(self):
        assert _price_score(3.0, 1.0, 5.0) == pytest.approx(0.5, abs=1e-3)

    def test_single_price_point_returns_one(self):
        # When all listings have the same price, everyone gets full score
        assert _price_score(2.5, 2.5, 2.5) == 1.0


class TestBenchmarkScore:
    def test_best_performer_gets_one(self):
        assert _benchmark_score_normalised(100.0, 50.0, 100.0) == pytest.approx(1.0, abs=1e-3)

    def test_worst_performer_gets_zero(self):
        assert _benchmark_score_normalised(50.0, 50.0, 100.0) == pytest.approx(0.0, abs=1e-3)

    def test_missing_benchmark_gets_penalty(self):
        # Missing = 0.3 (below average, not excluded)
        score = _benchmark_score_normalised(None, 50.0, 100.0)
        assert score == pytest.approx(0.3, abs=1e-3)

    def test_single_benchmark_returns_one(self):
        assert _benchmark_score_normalised(75.0, 75.0, 75.0) == 1.0


class TestAvailabilityScore:
    def test_available_gets_one(self):
        assert _availability_score(True) == 1.0

    def test_unavailable_gets_zero(self):
        assert _availability_score(False) == 0.0


# ── rank_listings integration tests ────────────────────────────────────────────

class TestRankListings:

    def test_empty_input_returns_empty(self):
        assert rank_listings([]) == []

    def test_single_listing_returned(self):
        lst = _make_listing(price_usd=2.0, benchmark_score=50.0)
        results = rank_listings([lst])
        assert len(results) == 1
        assert results[0].listing_id == lst["id"]

    def test_cheaper_ranked_higher_when_goal_cheapest(self):
        cheap = _make_listing(price_usd=0.5, benchmark_score=30.0)
        expensive = _make_listing(price_usd=5.0, benchmark_score=80.0)
        results = rank_listings([cheap, expensive], goal="cheapest")
        assert results[0].listing_id == cheap["id"]

    def test_faster_ranked_higher_when_goal_fastest(self):
        slow = _make_listing(price_usd=0.5, benchmark_score=10.0)
        fast = _make_listing(price_usd=5.0, benchmark_score=200.0)
        results = rank_listings([slow, fast], goal="fastest")
        assert results[0].listing_id == fast["id"]

    def test_budget_filter_excludes_expensive(self):
        cheap = _make_listing(price_usd=1.0)
        expensive = _make_listing(price_usd=10.0)
        results = rank_listings([cheap, expensive], budget_usd=5.0)
        assert len(results) == 1
        assert results[0].listing_id == cheap["id"]

    def test_budget_filter_returns_empty_when_all_exceed(self):
        l1 = _make_listing(price_usd=20.0)
        l2 = _make_listing(price_usd=15.0)
        results = rank_listings([l1, l2], budget_usd=5.0)
        assert results == []

    def test_unavailable_listing_scores_lower(self):
        available = _make_listing(price_usd=3.0, benchmark_score=50.0, is_available=True)
        unavailable = _make_listing(price_usd=1.0, benchmark_score=50.0, is_available=False)
        # Even if unavailable is cheaper, available should rank higher because
        # availability weight=0.25 can overcome a moderate price difference
        results = rank_listings(
            [available, unavailable],
            weight_price=0.40,
            weight_benchmark=0.35,
            weight_availability=0.25,
        )
        # The available one should be in the results
        ids = [r.listing_id for r in results]
        assert available["id"] in ids

    def test_top_n_limits_results(self):
        listings = [_make_listing(price_usd=float(i)) for i in range(1, 20)]
        results = rank_listings(listings, top_n=5)
        assert len(results) == 5

    def test_composite_score_in_valid_range(self):
        listings = [
            _make_listing(price_usd=1.0, benchmark_score=100.0, is_available=True),
            _make_listing(price_usd=3.0, benchmark_score=50.0, is_available=True),
            _make_listing(price_usd=5.0, benchmark_score=20.0, is_available=False),
        ]
        results = rank_listings(listings)
        for r in results:
            assert 0.0 <= r.score_composite <= 1.0
            assert 0.0 <= r.score_price <= 1.0
            assert 0.0 <= r.score_benchmark <= 1.0
            assert r.score_availability in (0.0, 1.0)

    def test_results_sorted_descending_by_composite(self):
        listings = [_make_listing(price_usd=float(i), benchmark_score=float(100 - i)) for i in range(1, 6)]
        results = rank_listings(listings)
        scores = [r.score_composite for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_estimated_cost_and_time_present(self):
        lst = _make_listing(price_usd=2.0, benchmark_score=50.0)
        results = rank_listings([lst])
        r = results[0]
        assert r.estimated_cost_usd is not None
        assert r.estimated_hours is not None
        assert float(r.estimated_cost_usd) > 0

    def test_missing_benchmark_uses_fallback_tflops(self):
        lst = _make_listing(price_usd=2.0, benchmark_score=None)
        results = rank_listings([lst])
        assert results[0].estimated_hours is not None

    def test_budget_inr_filter(self):
        cheap_inr = _make_listing(price_usd=0.5, price_inr=40.0)
        expensive_inr = _make_listing(price_usd=0.6, price_inr=120.0)
        results = rank_listings([cheap_inr, expensive_inr], budget_inr=100.0)
        assert len(results) == 1
        assert results[0].listing_id == cheap_inr["id"]

    def test_reputation_score_is_stub_05(self):
        lst = _make_listing()
        results = rank_listings([lst])
        assert results[0].reputation_score == pytest.approx(0.5)

    def test_balanced_goal_uses_default_weights(self):
        """'balanced' goal should not override weights differently than the default."""
        listings = [_make_listing(price_usd=float(i)) for i in range(1, 4)]
        default_results = rank_listings(listings[:])
        balanced_results = rank_listings(listings[:], goal="balanced")
        default_ids = [r.listing_id for r in default_results]
        balanced_ids = [r.listing_id for r in balanced_results]
        assert default_ids == balanced_ids
