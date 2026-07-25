"""
Monitoring Service — API routes.

Endpoints:
  GET /monitoring/metrics   Prometheus text-format scrape endpoint
  GET /monitoring/health    Health check with per-service status
  GET /monitoring/summary   Human-readable platform summary (active instances, spend today)
"""

import structlog
from fastapi import APIRouter
from fastapi.responses import Response

from services.monitoring_service.metrics import get_metrics_output

logger = structlog.get_logger(__name__)

monitoring_router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


# ── GET /monitoring/metrics ────────────────────────────────────────────────

@monitoring_router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus-compatible scrape endpoint.
    Grafana / Prometheus scrapes this every 15s to collect all platform metrics.
    No JWT required — restrict access at the network level (internal only).
    """
    content, content_type = get_metrics_output()
    return Response(content=content, media_type=content_type)


# ── GET /monitoring/health ─────────────────────────────────────────────────

@monitoring_router.get("/health")
async def platform_health():
    """
    Platform-wide health check.
    Returns status for each service component. Used by Grafana alerting.
    """
    # Phase 10: static OK response; in production, check each service /health endpoint
    return {
        "status": "ok",
        "services": {
            "api_gateway": "ok",
            "auth_service": "ok",
            "marketplace_service": "ok",
            "wallet_billing_service": "ok",
            "provisioning_service": "ok",
            "security_service": "ok",
            "ai_router_copilot_service": "ok",
            "reputation_pricing_service": "ok",
            "notifications_service": "ok",
            "monitoring_service": "ok",
        },
    }


# ── GET /monitoring/summary ────────────────────────────────────────────────

@monitoring_router.get("/summary")
async def platform_summary():
    """
    Human-readable platform summary for the admin dashboard.
    Phase 10: returns static structure; production populates from DB/Redis.
    """
    return {
        "active_instances": 0,
        "compute_spend_today_usd": "0.00",
        "wallet_topups_today": 0,
        "notifications_sent_today": 0,
        "invoices_generated_today": 0,
        "note": "Live data available after Grafana integration with DB queries.",
    }
