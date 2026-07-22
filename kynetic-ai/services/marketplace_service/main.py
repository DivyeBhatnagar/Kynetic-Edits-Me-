"""
Marketplace Service — FastAPI application entry point.
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from services.marketplace_service.config import get_settings
from services.marketplace_service.routes import router

settings = get_settings()
configure_logging(log_level=settings.log_level)
logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Kynetic AI — Marketplace Service",
    description="Compute-first marketplace: create, browse, and manage compute listings.",
    version="0.1.0",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/healthz", tags=["Health"])
async def health():
    return {"status": "ok", "service": "marketplace_service"}
