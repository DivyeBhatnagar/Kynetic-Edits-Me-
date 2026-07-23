"""
Monitoring Service — Prometheus metrics instrumentation.

Defines all platform-wide metrics using prometheus-client.

Metric naming convention: kynetic_{subsystem}_{metric_name}_{unit}

All metrics are registered in this module and imported by:
  - monitoring_service routes (to expose /metrics)
  - Other services (to record their own metrics)

Design: use the prometheus_client Registry directly so this module can
be safely imported across services without double-registration errors.
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    generate_latest,
)

# ── Registry (shared) ─────────────────────────────────────────────────────
# Use default registry in single-process mode; multiproc in production
REGISTRY = CollectorRegistry(auto_describe=False)


# ── Instance metrics ──────────────────────────────────────────────────────

instances_total = Counter(
    "kynetic_instances_total",
    "Total number of instances provisioned",
    ["status", "resource_type", "region"],
    registry=REGISTRY,
)

instances_active = Gauge(
    "kynetic_instances_active",
    "Number of currently active instances",
    ["resource_type", "region"],
    registry=REGISTRY,
)

instance_duration_seconds = Histogram(
    "kynetic_instance_duration_seconds",
    "Duration of instance runtime in seconds",
    ["resource_type", "region"],
    buckets=[60, 300, 900, 1800, 3600, 7200, 14400, 43200, 86400],
    registry=REGISTRY,
)


# ── GPU telemetry metrics ─────────────────────────────────────────────────

gpu_utilization_percent = Gauge(
    "kynetic_gpu_utilization_percent",
    "GPU utilization percentage by host",
    ["host_id", "gpu_model"],
    registry=REGISTRY,
)

gpu_vram_used_gb = Gauge(
    "kynetic_gpu_vram_used_gb",
    "VRAM used (GB) by host",
    ["host_id", "gpu_model"],
    registry=REGISTRY,
)

gpu_temperature_celsius = Gauge(
    "kynetic_gpu_temperature_celsius",
    "GPU temperature (°C) by host",
    ["host_id", "gpu_model"],
    registry=REGISTRY,
)


# ── Billing metrics ───────────────────────────────────────────────────────

wallet_topups_total = Counter(
    "kynetic_wallet_topups_total",
    "Total wallet top-up transactions",
    ["method", "currency"],   # method: stripe | razorpay_upi
    registry=REGISTRY,
)

wallet_topup_amount_usd = Counter(
    "kynetic_wallet_topup_amount_usd_total",
    "Total wallet top-up amount in USD",
    registry=REGISTRY,
)

compute_spend_usd = Counter(
    "kynetic_compute_spend_usd_total",
    "Total compute spend in USD by resource type",
    ["resource_type"],
    registry=REGISTRY,
)

invoices_generated_total = Counter(
    "kynetic_invoices_generated_total",
    "Total GST invoices generated",
    registry=REGISTRY,
)


# ── API request metrics ───────────────────────────────────────────────────

http_requests_total = Counter(
    "kynetic_http_requests_total",
    "Total HTTP requests by service, method, path, and status",
    ["service", "method", "path", "status_code"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "kynetic_http_request_duration_seconds",
    "HTTP request latency by service and path",
    ["service", "path"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)


# ── AI Router metrics ─────────────────────────────────────────────────────

router_recommendations_total = Counter(
    "kynetic_router_recommendations_total",
    "Total AI Router recommendations served",
    ["mode"],   # mode: budget | performance | balanced
    registry=REGISTRY,
)

router_no_results_total = Counter(
    "kynetic_router_no_results_total",
    "Total AI Router requests with no matching listings (fallback shown)",
    registry=REGISTRY,
)


# ── Notifications metrics ─────────────────────────────────────────────────

notifications_dispatched_total = Counter(
    "kynetic_notifications_dispatched_total",
    "Total notifications dispatched by type and channel",
    ["notification_type", "channel"],
    registry=REGISTRY,
)


# ── Helpers ───────────────────────────────────────────────────────────────

def get_metrics_output() -> tuple[bytes, str]:
    """Return (content_bytes, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
