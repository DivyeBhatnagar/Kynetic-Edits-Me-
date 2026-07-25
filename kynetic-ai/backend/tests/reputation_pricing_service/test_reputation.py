"""
Unit tests — reputation scoring engine.

Tests are pure Python — no DB, no network, no Celery.
"""

import pytest

from services.reputation_pricing_service.reputation import (
    DEFAULT_WEIGHTS,
    ReputationInputs,
    compute_reputation,
    _uptime_score,
    _latency_score,
    _network_score,
    _job_success_score,
    _benchmark_normalised,
    _response_time_score,
)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _full_inputs(**overrides) -> ReputationInputs:
    """Return a fully-specified ReputationInputs with excellent telemetry."""
    base = dict(
        heartbeats_received=43_200,   # 30d × 1440/day
        heartbeats_expected=43_200,
        provisioning_latency_p99_ms=1_500.0,  # below BEST → 1.0
        network_throughput_mbps=1_000.0,      # at BEST → 1.0
        jobs_completed=50,
        jobs_total=50,
        benchmark_raw=1.0,                    # max of class → normalises to 1.0
        benchmark_class_min=0.0,
        benchmark_class_max=1.0,
        avg_agent_response_ms=3_000.0,        # below BEST → 1.0
    )
    base.update(overrides)
    return ReputationInputs(**base)


# ── Component-level tests ──────────────────────────────────────────────────────

class TestUptimeScore:
    def test_perfect_uptime(self):
        assert _uptime_score(1440, 1440) == 1.0

    def test_half_uptime(self):
        assert _uptime_score(720, 1440) == pytest.approx(0.5, abs=1e-6)

    def test_zero_heartbeats(self):
        assert _uptime_score(0, 1440) == 0.0

    def test_expected_zero_returns_zero(self):
        assert _uptime_score(100, 0) == 0.0

    def test_excess_heartbeats_clamped_to_one(self):
        # More received than expected (e.g., missed beat filled in by retry) → clamped
        assert _uptime_score(2000, 1440) == 1.0


class TestLatencyScore:
    def test_perfect_latency(self):
        assert _latency_score(500.0) == 1.0

    def test_worst_latency(self):
        assert _latency_score(60_000.0) == 0.0

    def test_midpoint_latency(self):
        # (60000 - 31000) / (60000 - 2000) = 29000/58000 ≈ 0.5
        assert _latency_score(31_000.0) == pytest.approx(0.5, abs=0.01)

    def test_none_latency_returns_none(self):
        assert _latency_score(None) is None

    def test_at_best_boundary(self):
        assert _latency_score(2_000.0) == 1.0


class TestNetworkScore:
    def test_gigabit_is_perfect(self):
        assert _network_score(1_000.0) == 1.0

    def test_below_worst_is_zero(self):
        assert _network_score(5.0) == 0.0

    def test_none_returns_none(self):
        assert _network_score(None) is None

    def test_midpoint(self):
        # (505 - 10) / (1000 - 10) = 495/990 = 0.5
        assert _network_score(505.0) == pytest.approx(0.5, abs=0.01)


class TestJobSuccessScore:
    def test_all_completed(self):
        assert _job_success_score(100, 100) == 1.0

    def test_no_jobs_returns_none(self):
        assert _job_success_score(0, 0) is None

    def test_half_success(self):
        assert _job_success_score(5, 10) == pytest.approx(0.5, abs=1e-6)

    def test_zero_completed(self):
        assert _job_success_score(0, 10) == 0.0


class TestBenchmarkNormalised:
    def test_max_score(self):
        assert _benchmark_normalised(1.0, 0.0, 1.0) == 1.0

    def test_min_score(self):
        assert _benchmark_normalised(0.0, 0.0, 1.0) == 0.0

    def test_none_returns_none(self):
        assert _benchmark_normalised(None, 0.0, 1.0) is None

    def test_single_class_member(self):
        # Only one machine in class → always 1.0
        assert _benchmark_normalised(5.0, 5.0, 5.0) == 1.0

    def test_midpoint(self):
        assert _benchmark_normalised(0.5, 0.0, 1.0) == pytest.approx(0.5, abs=1e-6)


class TestResponseTimeScore:
    def test_fast_response(self):
        assert _response_time_score(1_000.0) == 1.0

    def test_too_slow(self):
        assert _response_time_score(200_000.0) == 0.0

    def test_none_returns_none(self):
        assert _response_time_score(None) is None


# ── Composite / compute_reputation tests ──────────────────────────────────────

class TestComputeReputation:
    def test_perfect_host_score_is_one(self):
        # benchmark_raw=1.0 so all six components normalise to 1.0 → composite=1.0
        inputs = _full_inputs(benchmark_raw=1.0)
        result = compute_reputation(inputs)
        assert result.composite_score == pytest.approx(1.0, abs=0.01)

    def test_all_components_present_for_full_host(self):
        result = compute_reputation(_full_inputs())
        assert result.uptime_score is not None
        assert result.latency_score is not None
        assert result.network_score is not None
        assert result.job_success_rate is not None
        assert result.benchmark_score_normalised is not None
        assert result.response_time_score is not None

    def test_null_job_telemetry_excluded_from_composite(self):
        """
        Host with no jobs yet should still get a fair composite from the
        other five components — not penalised for absence.
        """
        inputs = _full_inputs(jobs_completed=0, jobs_total=0)
        result = compute_reputation(inputs)
        # With job_success excluded (NULL), remaining weights re-normalise to 1.0
        # All other components are perfect → composite should be close to 1.0
        assert result.composite_score >= 0.9
        assert result.job_success_rate is None

    def test_null_latency_excluded(self):
        inputs = _full_inputs(provisioning_latency_p99_ms=None)
        result = compute_reputation(inputs)
        assert result.latency_score is None
        assert result.composite_score >= 0.85

    def test_zero_uptime_lowers_composite(self):
        inputs = _full_inputs(heartbeats_received=0)
        result = compute_reputation(inputs)
        # uptime_score = 0.0, weight 0.30 — composite should drop significantly
        assert result.uptime_score == 0.0
        assert result.composite_score < 0.8

    def test_all_null_telemetry_returns_zero(self):
        inputs = ReputationInputs(
            heartbeats_received=0,
            heartbeats_expected=0,
            provisioning_latency_p99_ms=None,
            network_throughput_mbps=None,
            jobs_completed=0,
            jobs_total=0,
            benchmark_raw=None,
            avg_agent_response_ms=None,
        )
        result = compute_reputation(inputs)
        # Only uptime is present (and is 0), the rest are NULL → composite = 0.0
        assert result.composite_score == pytest.approx(0.0, abs=1e-6)

    def test_custom_weights_respected(self):
        # Give all weight to job_success (=1.0 for perfect host)
        custom_weights = {
            "uptime": 0.0,
            "latency": 0.0,
            "network": 0.0,
            "job_success": 1.0,
            "benchmark": 0.0,
            "response_time": 0.0,
        }
        inputs = _full_inputs()
        result = compute_reputation(inputs, weights=custom_weights)
        assert result.composite_score == pytest.approx(1.0, abs=1e-6)

    def test_composite_clamped_to_one(self):
        """Composite should never exceed 1.0 even with floating-point drift."""
        inputs = _full_inputs()
        result = compute_reputation(inputs)
        assert result.composite_score <= 1.0

    def test_composite_non_negative(self):
        inputs = _full_inputs(
            heartbeats_received=0,
            provisioning_latency_p99_ms=120_000.0,
            network_throughput_mbps=0.0,
        )
        result = compute_reputation(inputs)
        assert result.composite_score >= 0.0

    def test_result_exposes_all_six_components(self):
        result = compute_reputation(_full_inputs())
        assert hasattr(result, "uptime_score")
        assert hasattr(result, "latency_score")
        assert hasattr(result, "network_score")
        assert hasattr(result, "job_success_rate")
        assert hasattr(result, "benchmark_score_normalised")
        assert hasattr(result, "response_time_score")
        assert hasattr(result, "composite_score")

    def test_bad_benchmark_bounds_safe(self):
        """If class min == max (only one machine), score should be 1.0, not divide-by-zero."""
        inputs = _full_inputs(benchmark_raw=5.0, benchmark_class_min=5.0, benchmark_class_max=5.0)
        result = compute_reputation(inputs)
        assert result.benchmark_score_normalised == 1.0

    @pytest.mark.parametrize("jobs_total,jobs_done,expected_rate", [
        (100, 100, 1.0),
        (100, 90, 0.9),
        (100, 50, 0.5),
        (100, 0, 0.0),
    ])
    def test_job_success_rate_parametrized(self, jobs_total, jobs_done, expected_rate):
        inputs = _full_inputs(jobs_total=jobs_total, jobs_completed=jobs_done)
        result = compute_reputation(inputs)
        assert result.job_success_rate == pytest.approx(expected_rate, abs=1e-6)
