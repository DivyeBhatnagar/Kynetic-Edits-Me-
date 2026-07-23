"""
reputation_pricing_service — FastAPI application entry point.
Port: 8008
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIDMiddleware
from services.reputation_pricing_service.config import get_settings
from services.reputation_pricing_service.routes import (
    dashboard_router,
    pricing_router,
    reputation_router,
)

configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Kynetic AI — Reputation & Auto-Pricing Service",
    description=(
        "Phase 8: Transparent host reputation scoring (uptime, latency, network, "
        "job success, benchmark, response time) + scikit-learn auto-pricing engine + "
        "idle time prediction + income projection."
    ),
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(CorrelationIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reputation_router, prefix="/v1")
app.include_router(dashboard_router, prefix="/v1")
app.include_router(pricing_router, prefix="/v1")


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok", "service": "reputation_pricing_service"}


@app.on_event("startup")
async def on_startup():
    log.info(
        "reputation_pricing_service.starting",
        environment=settings.environment,
        pricing_floor_usd=str(settings.pricing_floor_usd),
        pricing_cap_usd=str(settings.pricing_cap_usd),
    )
