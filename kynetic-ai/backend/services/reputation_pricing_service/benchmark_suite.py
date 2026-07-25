"""
v8 Feature 1 — GPU Benchmark & Health Score Engine.

Pure-Python scoring / normalisation layer.  No I/O, no SQLAlchemy — fully
unit-testable in isolation.

Key design decisions (from §1 of Implementation Plan v8):

1. PEER-GROUP NORMALISATION
   A 4090 is scored relative to other 4090s, not against an H100.
   Each metric is min-max normalised within the GPU-model peer group.

2. MISSING-DATA POLICY
   If any sub-metric has no data, it is excluded from the weighted average
   (same approach as reputation.py's re-normalised composite).  A host with
   zero benchmark runs gets performance_score = None, not 0.

3. FRAUD / ENVELOPE CHECKS  (§1.11, §1.16)
   Each raw result is checked against the admin-maintained GpuModelEnvelope.
   A result outside [min_value, max_value] → BenchmarkFlag with reason.
   Envelope check is conservative: if no envelope exists for a (model, type)
   pair, the result is accepted (ok) without flagging.

4. HEALTH SCORE  (§1.2, §1.9)
   Derived from the rolling 7-day heartbeat window, not a discrete benchmark.
   Three stability sub-scores: thermal, clock, power.  Defined as the
   inverse of the coefficient of variation (CV) — a stable signal has low CV,
   which maps to a high stability score.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Sequence

import structlog

log = structlog.get_logger(__name__)


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class BenchmarkRunInput:
    """A single sub-test result reported by the Host Agent."""
    benchmark_type: str          # e.g. "gpu_fp16_tflops"
    value: float
    unit: str
    gpu_model: str | None = None
    cuda_version: str | None = None
    driver_version: str | None = None


@dataclass
class PeerEnvelope:
    """
    Performance envelope for one (gpu_model, benchmark_type) pair.
    Populated from GpuModelEnvelope rows; if no row exists for a pair,
    the check is skipped (see check_envelope).
    """
    gpu_model: str
    benchmark_type: str
    min_value: float
    max_value: float
    unit: str
    # Peer-group sample statistics (from host_benchmark_runs aggregation)
    peer_min: float | None = None   # lowest observed value in the peer group
    peer_max: float | None = None   # highest observed value
    peer_count: int = 0             # number of hosts in peer group


@dataclass
class BenchmarkFlag:
    """Returned when check_envelope detects a suspicious result."""
    benchmark_type: str
    value: float
    reason: str
    severity: str = "flagged"      # "flagged" | "skipped"


@dataclass
class HeartbeatSample:
    """A single heartbeat row used for health score computation."""
    gpu_temperature_celsius: float | None = None
    cpu_temperature_celsius: float | None = None
    power_draw_watts: float | None = None
    gpu_core_clock_mhz: float | None = None


@dataclass
class PerformanceScoreResult:
    """
    Structured output of compute_performance_score.
    All component values are in [0.0, 1.0] or None.
    """
    performance_score: float | None
    fp16_tflops_normalised: float | None
    fp32_tflops_normalised: float | None
    mem_bandwidth_normalised: float | None
    peer_group_size: int
    flags: list[BenchmarkFlag] = field(default_factory=list)


@dataclass
class HealthScoreResult:
    """Structured output of compute_health_score."""
    health_score: float | None
    thermal_stability_score: float | None
    clock_stability_score: float | None
    power_stability_score: float | None
    samples_used: int


# ── Weights ────────────────────────────────────────────────────────────────────

# Performance sub-score weights (sum to 1.0)
PERF_WEIGHTS: dict[str, float] = {
    "gpu_fp16_tflops": 0.40,
    "gpu_fp32_tflops": 0.35,
    "gpu_mem_bandwidth_gbps": 0.25,
}

# Health sub-score weights (sum to 1.0)
HEALTH_WEIGHTS: dict[str, float] = {
    "thermal": 0.40,
    "clock": 0.35,
    "power": 0.25,
}


# ── Normalisation helpers ──────────────────────────────────────────────────────

def _minmax_normalise(value: float, low: float, high: float) -> float:
    """
    Map value to [0.0, 1.0] using min-max normalisation.
    If low == high (single sample or degenerate range), return 1.0
    (the host is the best in its class by default).
    """
    if high <= low:
        return 1.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _cv_to_stability(values: list[float]) -> float | None:
    """
    Convert a list of telemetry samples to a stability score in [0.0, 1.0].

    Stability = 1 − CV, where CV = std / mean (coefficient of variation).

    Thresholds:
      CV = 0%    → stability = 1.0  (perfectly constant)
      CV = 20%   → stability = 0.0  (highly variable)
      Between → linear interpolation.

    Returns None if fewer than 3 samples (insufficient signal).
    """
    clean = [v for v in values if v is not None and v > 0]
    if len(clean) < 3:
        return None
    mean = statistics.mean(clean)
    if mean == 0:
        return None
    std = statistics.pstdev(clean)
    cv = std / mean
    # CV=0 → 1.0, CV≥0.20 → 0.0
    MAX_CV = 0.20
    stability = max(0.0, min(1.0, 1.0 - (cv / MAX_CV)))
    return stability


# ── Envelope check (fraud detection) ──────────────────────────────────────────

def check_envelope(
    run: BenchmarkRunInput,
    envelope: PeerEnvelope | None,
) -> BenchmarkFlag | None:
    """
    Check whether `run.value` falls within the expected hardware envelope for
    this (gpu_model, benchmark_type) pair.

    Returns a BenchmarkFlag if the result is suspicious; None if it is ok.

    If `envelope` is None (no admin-defined range for this pair), the result
    is accepted — we never flag what we can't verify.

    §1.11 / §1.16 of the v8 Implementation Plan.
    """
    if envelope is None:
        return None

    if run.value < envelope.min_value:
        return BenchmarkFlag(
            benchmark_type=run.benchmark_type,
            value=run.value,
            reason=(
                f"Value {run.value:.2f} {run.unit} is below the expected minimum "
                f"{envelope.min_value:.2f} for GPU model '{envelope.gpu_model}' — "
                "possible hardware mismatch or throttling."
            ),
            severity="flagged",
        )

    if run.value > envelope.max_value:
        return BenchmarkFlag(
            benchmark_type=run.benchmark_type,
            value=run.value,
            reason=(
                f"Value {run.value:.2f} {run.unit} exceeds the expected maximum "
                f"{envelope.max_value:.2f} for GPU model '{envelope.gpu_model}' — "
                "possible spoofed or fabricated result."
            ),
            severity="flagged",
        )

    return None


# ── Performance Score ──────────────────────────────────────────────────────────

def compute_performance_score(
    runs: Sequence[BenchmarkRunInput],
    envelopes: dict[str, PeerEnvelope] | None = None,
    weights: dict[str, float] | None = None,
) -> PerformanceScoreResult:
    """
    Compute the Performance Score for a host from its latest sub-test results.

    Normalisation strategy:
      - Uses the peer-group peer_min / peer_max from the PeerEnvelope if
        available (reflects actual fleet performance range for this GPU model).
      - Falls back to envelope.min_value / max_value (the admin-defined safe
        range) if peer stats are absent.
      - If neither is available, the sub-test is excluded from the composite.

    Parameters:
        runs: The sub-test results from the most recent benchmark suite run.
        envelopes: Optional dict of {benchmark_type: PeerEnvelope}.  If None
            or a type is missing, that sub-test is included without normalisation
            (treated as 0.5 = mid-range) if it passes the presence check, or
            excluded if we have no normalisation anchors at all.
        weights: Sub-test weights; defaults to PERF_WEIGHTS.

    Returns:
        PerformanceScoreResult with per-sub-metric breakdowns.

    §1.9 — Backend Changes
    """
    w = weights or PERF_WEIGHTS
    env = envelopes or {}

    # Index latest runs by type (last one wins if duplicates exist)
    by_type: dict[str, BenchmarkRunInput] = {}
    for run in runs:
        by_type[run.benchmark_type] = run

    flags: list[BenchmarkFlag] = []

    # Check all supplied runs for envelope violations (not just the perf sub-tests)
    for btype, run in by_type.items():
        envelope = env.get(btype)
        flag = check_envelope(run, envelope)
        if flag:
            flags.append(flag)

    # Normalise the three primary performance metrics
    def _normalise_metric(btype: str) -> float | None:
        run = by_type.get(btype)
        if run is None:
            return None
        envelope = env.get(btype)
        if envelope is None:
            # First machine in class / no peer data yet — treat as best in class (1.0)
            return 1.0
        low = envelope.peer_min if envelope.peer_min is not None else envelope.min_value
        high = envelope.peer_max if envelope.peer_max is not None else envelope.max_value
        return _minmax_normalise(run.value, low, high)

    fp16 = _normalise_metric("gpu_fp16_tflops")
    fp32 = _normalise_metric("gpu_fp32_tflops")
    mem_bw = _normalise_metric("gpu_mem_bandwidth_gbps")

    sub_scores: dict[str, float | None] = {
        "gpu_fp16_tflops": fp16,
        "gpu_fp32_tflops": fp32,
        "gpu_mem_bandwidth_gbps": mem_bw,
    }

    # Re-normalised weighted composite (same approach as reputation.py)
    present = {k: v for k, v in sub_scores.items() if v is not None}
    total_weight = sum(w.get(k, 0.0) for k in present)

    if total_weight == 0.0 or not present:
        perf_score = None
    else:
        perf_score = sum(
            (w.get(k, 0.0) / total_weight) * v
            for k, v in present.items()
        )
        perf_score = max(0.0, min(1.0, perf_score))

    # Determine peer_group_size (max across available envelopes)
    peer_group_size = max(
        (env[t].peer_count for t in ["gpu_fp16_tflops", "gpu_fp32_tflops", "gpu_mem_bandwidth_gbps"] if t in env),
        default=0,
    )

    log.debug(
        "benchmark.performance_score",
        fp16=round(fp16, 4) if fp16 is not None else None,
        fp32=round(fp32, 4) if fp32 is not None else None,
        mem_bw=round(mem_bw, 4) if mem_bw is not None else None,
        composite=round(perf_score, 4) if perf_score is not None else None,
        flags=[f.benchmark_type for f in flags],
    )

    return PerformanceScoreResult(
        performance_score=perf_score,
        fp16_tflops_normalised=fp16,
        fp32_tflops_normalised=fp32,
        mem_bandwidth_normalised=mem_bw,
        peer_group_size=peer_group_size,
        flags=flags,
    )


# ── Health Score ───────────────────────────────────────────────────────────────

def compute_health_score(
    heartbeats: Sequence[HeartbeatSample],
    weights: dict[str, float] | None = None,
) -> HealthScoreResult:
    """
    Compute the Health Score from a rolling window of heartbeat samples.

    The health score captures *sustained thermal/power/clock stability* —
    not a point-in-time snapshot.  It measures whether the host's hardware
    behaves consistently under load over the trailing 7-day window.

    Three sub-scores:
      thermal  — GPU + CPU temperature stability (combined CV)
      clock    — GPU core clock stability (CV of clock readings)
      power    — Power draw stability (CV)

    Each is the inverse of CV, mapped to [0.0, 1.0] via _cv_to_stability.
    NULL sub-scores are excluded from the weighted composite (same policy as
    performance_score and reputation.py composite).

    Minimum sample requirement: 3 samples per sub-score; fewer → None.

    §1.2 / §1.9 of the v8 Implementation Plan.
    """
    w = weights or HEALTH_WEIGHTS

    # ── Thermal stability ─────────────────────────────────────────────────────
    gpu_temps = [h.gpu_temperature_celsius for h in heartbeats if h.gpu_temperature_celsius is not None]
    cpu_temps = [h.cpu_temperature_celsius for h in heartbeats if h.cpu_temperature_celsius is not None]
    gpu_thermal = _cv_to_stability(gpu_temps)
    cpu_thermal = _cv_to_stability(cpu_temps)
    if gpu_thermal is not None and cpu_thermal is not None:
        thermal = (gpu_thermal + cpu_thermal) / 2.0
    elif gpu_thermal is not None:
        thermal = gpu_thermal
    else:
        thermal = cpu_thermal

    # ── Clock stability ───────────────────────────────────────────────────────
    clocks = [h.gpu_core_clock_mhz for h in heartbeats if h.gpu_core_clock_mhz is not None]
    clock = _cv_to_stability(clocks)

    # ── Power stability ───────────────────────────────────────────────────────
    powers = [h.power_draw_watts for h in heartbeats if h.power_draw_watts is not None]
    power = _cv_to_stability(powers)

    sub_scores: dict[str, float | None] = {
        "thermal": thermal,
        "clock": clock,
        "power": power,
    }

    present = {k: v for k, v in sub_scores.items() if v is not None}
    total_weight = sum(w.get(k, 0.0) for k in present)

    if total_weight == 0.0 or not present:
        health = None
    else:
        health = sum(
            (w.get(k, 0.0) / total_weight) * v
            for k, v in present.items()
        )
        health = max(0.0, min(1.0, health))

    log.debug(
        "benchmark.health_score",
        thermal=round(thermal, 4) if thermal is not None else None,
        clock=round(clock, 4) if clock is not None else None,
        power=round(power, 4) if power is not None else None,
        composite=round(health, 4) if health is not None else None,
        samples=len(heartbeats),
    )

    return HealthScoreResult(
        health_score=health,
        thermal_stability_score=thermal,
        clock_stability_score=clock,
        power_stability_score=power,
        samples_used=len(heartbeats),
    )


# ── Composite host score ───────────────────────────────────────────────────────

# Weights for the HostScore composite (§1.9 — Performance Score + Health Score)
HOST_SCORE_WEIGHTS: dict[str, float] = {
    "performance": 0.50,
    "health": 0.30,
    "reliability": 0.20,
}


def compute_host_composite(
    performance_score: float | None,
    health_score: float | None,
    reliability_score: float | None,
    weights: dict[str, float] | None = None,
) -> float | None:
    """
    Combine the three first-class scores into the HostScore composite.

    reliability_score is sourced from `reputation_scores.composite_score`
    (the existing reputation engine) so this function does not recompute it.
    NULL inputs are excluded (re-normalised weights).

    Returns None only if all three inputs are None.
    """
    w = weights or HOST_SCORE_WEIGHTS
    components: dict[str, float | None] = {
        "performance": performance_score,
        "health": health_score,
        "reliability": reliability_score,
    }
    present = {k: v for k, v in components.items() if v is not None}
    total_weight = sum(w.get(k, 0.0) for k in present)

    if total_weight == 0.0 or not present:
        return None

    composite = sum(
        (w.get(k, 0.0) / total_weight) * v
        for k, v in present.items()
    )
    return max(0.0, min(1.0, composite))
