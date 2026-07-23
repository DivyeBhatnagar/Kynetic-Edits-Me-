"""
AI Router & Copilot Service — FastAPI Application Entry Point.
Port: 8007

Middleware stack (applied in reverse order, outermost first):
  1. CORSMiddleware       — permissive in dev, locked-down in prod
  2. CorrelationIDMiddleware — propagates X-Correlation-ID
  3. RateLimiterMiddleware  — per-route limits with route-specific overrides
     /router/*   → 30 RPM (Phase 7 spec explicit requirement)
     /copilot/*  → 20 RPM (Phase 7 spec explicit requirement)
     default     → 60 RPM
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIDMiddleware
from services.ai_router_copilot_service.config import get_settings
from services.ai_router_copilot_service.copilot_routes import copilot_router
from services.ai_router_copilot_service.router_routes import router_router
from services.api_gateway.rate_limiter import RateLimitConfig, RateLimiterMiddleware

configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Kynetic AI — AI Resource Router & Copilot",
    description=(
        "Phase 7: AI Resource Router (budget/goal-based machine recommendations) "
        "and AI Copilot (conversational interface with grounded cost/time estimates)."
    ),
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

# ── Rate Limiting (Phase 5/7 explicit requirement) ────────────────────────────
# /router/* and /copilot/* have stricter limits than the global default.
_rate_config = RateLimitConfig(
    redis_url=settings.redis_url,
    default_rpm=60,
    burst=settings.rate_limit_burst,
)
_rate_config.route_limits["/router"] = settings.router_rpm
_rate_config.route_limits["/copilot"] = settings.copilot_rpm

app.add_middleware(RateLimiterMiddleware, config=_rate_config)
app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(router_router, prefix="/v1")
app.include_router(copilot_router, prefix="/v1")


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok", "service": "ai_router_copilot_service"}


@app.on_event("startup")
async def on_startup():
    log.info(
        "ai_router_copilot_service.starting",
        environment=settings.environment,
        llm_backend=settings.llm_backend,
        router_rpm=settings.router_rpm,
        copilot_rpm=settings.copilot_rpm,
    )
