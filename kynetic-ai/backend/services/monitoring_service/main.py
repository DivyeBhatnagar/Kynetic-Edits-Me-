"""
Monitoring Service — FastAPI application.

Port: 8011 (internal only)
Prometheus scrapes GET /monitoring/metrics every 15s.
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.monitoring_service.routes import monitoring_router

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Kynetic Monitoring Service",
    description="Prometheus metrics scrape endpoint and platform health checks.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(monitoring_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "monitoring_service"}
