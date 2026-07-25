"""
Shared Library — Prometheus Observability Metrics (metrics.py)

Exposes platform OpenTelemetry and Prometheus counters, gauges, and histograms.
"""

from typing import Dict
import structlog

log = structlog.get_logger(__name__)


class MetricsCollector:
    """
    In-memory Prometheus metrics registry.
    """

    def __init__(self):
        self._gauges: Dict[str, float] = {
            "kynetic_instances_active_total": 0.0,
            "kynetic_hosts_verified_total": 0.0,
            "kynetic_gateway_pty_sessions_active": 0.0,
        }
        self._counters: Dict[str, float] = {
            "kynetic_metered_seconds_total": 0.0,
            "kynetic_requests_total": 0.0,
        }

    def set_gauge(self, name: str, value: float) -> None:
        self._gauges[name] = float(value)

    def inc_counter(self, name: str, amount: float = 1.0) -> None:
        self._counters[name] = self._counters.get(name, 0.0) + float(amount)

    def export_prometheus_text(self) -> str:
        lines = []
        for k, v in self._gauges.items():
            lines.append(f"# TYPE {k} gauge\n{k} {v}")
        for k, v in self._counters.items():
            lines.append(f"# TYPE {k} counter\n{k} {v}")
        return "\n".join(lines) + "\n"


metrics = MetricsCollector()
