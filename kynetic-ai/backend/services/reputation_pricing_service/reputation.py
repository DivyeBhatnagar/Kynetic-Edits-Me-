"""
Reputation scoring engine — Phase 8.

Design decisions:
  1. TRANSPARENT WEIGHTED SCORING (not a black box).
     Per Phase 8 spec: "trust-critical scoring must be explainable."
     Every component score is independently computed, labelled, and returned
     to the caller. The composite formula is public.

  2. FRAUD-RESISTANT INPUTS (Security Pillar 6).
     All six inputs come from already-verified telemetry tables
     (host_heartbeats, host_benchmarks, instances) — zero self-reported fields.

  3. MISSING TELEMETRY POLICY.
     If a component has no data (e.g., host has never run a job), the component
     score is NULL and is excluded from the weighted average rather than dragging
     the composite to zero. The weights of present components are re-normalised.

  4. NORMALISATION.
     All raw values are mapped to [0.0, 1.0] via min-max or inverse-linear
     transformations with empirically-sensible bounds documented in-code.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

# ── Default component weights ──────────────────────────────────────────────────
# Can be overridden at call-site (e.g., from settings) to allow A/B testing.

DEFAULT_WEIGHTS: dict[str, float] = {
    "uptime": 0.30,
    "latency": 0.15,
    "network": 0.10,
    "job_success": 0.25,
    "benchmark": 0.10,
    "response_time": 0.10,
}


# ── Raw → normalised score helpers ─────────────────────────────────────────────

def _uptime_score(heartbeats_received: int, heartbeats_expected: int) -> float:
    """
    Fraction of expected heartbeats received in the window.

    Expected heartbeats_expected = uptime_window_days × expected_heartbeats_per_day.
    Clamped to [0, 1].
    """
    if heartbeats_expected <= 0:
        return 0.0
    return min(1.0, heartbeats_received / heartbeats_expected)


def _latency_score(p99_ms: float | None) -> float | None:
    """
    Inverse-linear mapping of provisioning p99 latency:
      ≤ 2 000 ms → 1.0
      ≥ 60 000 ms → 0.0

    NULL input → NULL (no telemetry available).
    """
    if p99_ms is None:
        return None
    BEST = 2_000.0     # ms — fully responsive
    WORST = 60_000.0   # ms — unacceptably slow
    if p99_ms <= BEST:
        return 1.0
    if p99_ms >= WORST:
        return 0.0
    return (WORST - p99_ms) / (WORST - BEST)


def _network_score(throughput_mbps: float | None) -> float | None:
    """
    Forward-linear mapping of observed network throughput:
      ≥ 1 000 Mbps → 1.0
      ≤ 10 Mbps   → 0.0
    """
    if throughput_mbps is None:
        return None
    BEST = 1_000.0    # Mbps
    WORST = 10.0
    if throughput_mbps >= BEST:
        return 1.0
    if throughput_mbps <= WORST:
        return 0.0
    return (throughput_mbps - WORST) / (BEST - WORST)


def _job_success_score(completed: int, total: int) -> float | None:
    """
    Raw success rate = completed / total.  NULL if no jobs ever run.
    """
    if total <= 0:
        return None
    return min(1.0, completed / total)


def _benchmark_normalised(
    raw_score: float | None,
    min_score: float,
    max_score: float,
) -> float | None:
    """
    Min-max normalise a raw benchmark score against the floor/ceiling
    for that GPU class.  NULL if no benchmark data exists.
    """
    if raw_score is None:
        return None
    if max_score <= min_score:
        return 1.0  # Only one machine in class — treat as best
    return max(0.0, min(1.0, (raw_score - min_score) / (max_score - min_score)))


def _response_time_score(avg_response_ms: float | None) -> float | None:
    """
    How quickly the host agent acknowledges a provisioning request.
      ≤ 5 000 ms  → 1.0
      ≥ 120 000 ms → 0.0
    """
    if avg_response_ms is None:
        return None
    BEST = 5_000.0
    WORST = 120_000.0
    if avg_response_ms <= BEST:
        return 1.0
    if avg_response_ms >= WORST:
        return 0.0
    return (WORST - avg_response_ms) / (WORST - BEST)


# ── Composite computation ──────────────────────────────────────────────────────

class ReputationInputs:
    """
    All raw telemetry inputs needed to compute a host's reputation score.
    All fields are optional so callers can pass only what they have.
    """

    def __init__(
        self,
        heartbeats_received: int = 0,
        heartbeats_expected: int = 0,
        provisioning_latency_p99_ms: float | None = None,
        network_throughput_mbps: float | None = None,
        jobs_completed: int = 0,
        jobs_total: int = 0,
        benchmark_raw: float | None = None,
        benchmark_class_min: float = 0.0,
        benchmark_class_max: float = 1.0,
        avg_agent_response_ms: float | None = None,
    ):
        self.heartbeats_received = heartbeats_received
        self.heartbeats_expected = heartbeats_expected
        self.provisioning_latency_p99_ms = provisioning_latency_p99_ms
        self.network_throughput_mbps = network_throughput_mbps
        self.jobs_completed = jobs_completed
        self.jobs_total = jobs_total
        self.benchmark_raw = benchmark_raw
        self.benchmark_class_min = benchmark_class_min
        self.benchmark_class_max = benchmark_class_max
        self.avg_agent_response_ms = avg_agent_response_ms


class ReputationResult:
    """Output of compute_reputation — all components + composite."""

    def __init__(self, components: dict[str, float | None], composite: float):
        self.uptime_score = components.get("uptime")
        self.latency_score = components.get("latency")
        self.network_score = components.get("network")
        self.job_success_rate = components.get("job_success")
        self.benchmark_score_normalised = components.get("benchmark")
        self.response_time_score = components.get("response_time")
        self.composite_score = composite
        self._components = components


def compute_reputation(
    inputs: ReputationInputs,
    weights: dict[str, float] | None = None,
) -> ReputationResult:
    """
    Compute the six-component reputation score and the weighted composite.

    The composite uses re-normalised weights so that NULL components
    (missing telemetry) don't penalise hosts — they are simply excluded
    from the weighted average.

    Returns a ReputationResult with all components and the composite.
    """
    w = weights or DEFAULT_WEIGHTS

    # Compute each component
    components: dict[str, float | None] = {
        "uptime": _uptime_score(inputs.heartbeats_received, inputs.heartbeats_expected),
        "latency": _latency_score(inputs.provisioning_latency_p99_ms),
        "network": _network_score(inputs.network_throughput_mbps),
        "job_success": _job_success_score(inputs.jobs_completed, inputs.jobs_total),
        "benchmark": _benchmark_normalised(
            inputs.benchmark_raw,
            inputs.benchmark_class_min,
            inputs.benchmark_class_max,
        ),
        "response_time": _response_time_score(inputs.avg_agent_response_ms),
    }

    # Re-normalise weights for present (non-NULL) components
    present = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(w.get(k, 0.0) for k in present)

    if total_weight == 0.0 or not present:
        composite = 0.0
    else:
        composite = sum(
            (w.get(k, 0.0) / total_weight) * v for k, v in present.items()
        )

    # Clamp to [0, 1]
    composite = max(0.0, min(1.0, composite))

    log.debug(
        "reputation.computed",
        components={k: round(v, 4) if v is not None else None for k, v in components.items()},
        composite=round(composite, 4),
    )

    return ReputationResult(components=components, composite=composite)
