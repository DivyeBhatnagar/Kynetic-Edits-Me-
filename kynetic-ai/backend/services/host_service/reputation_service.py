"""
Host Service — Reputation Scoring Service (reputation_service.py)

Calculates Host Reputation Score (0.0 to 100.0) based on:
1. Uptime / Heartbeat Reliability (35%)
2. Benchmark Performance Consistency (25%)
3. Rental Completion Success Rate (25%)
4. Account Age / Verification Stability (15%)
"""

import structlog

log = structlog.get_logger(__name__)


class ReputationCalculator:
    """
    Computes weighted reputation score for host ranking (§9 & Section 14).
    """

    @staticmethod
    def calculate_score(
        uptime_pct: float = 100.0,
        benchmark_consistency_pct: float = 100.0,
        completion_rate_pct: float = 100.0,
        days_verified: int = 30,
    ) -> float:
        """
        Returns normalized reputation score (0.0 to 100.0).
        """
        w_uptime = (min(max(uptime_pct, 0.0), 100.0) / 100.0) * 35.0
        w_bench = (min(max(benchmark_consistency_pct, 0.0), 100.0) / 100.0) * 25.0
        w_completion = (min(max(completion_rate_pct, 0.0), 100.0) / 100.0) * 25.0
        w_age = (min(days_verified / 30.0, 1.0)) * 15.0

        total_score = round(w_uptime + w_bench + w_completion + w_age, 2)
        log.debug("reputation.calculated", score=total_score)
        return total_score
