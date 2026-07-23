"""
Provisioning Service — FastAPI Application Entry Point.
Port: 8005
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIDMiddleware
from services.provisioning_service.config import get_settings
from services.provisioning_service.routes import callback_router, provisioning_router
from services.provisioning_service.template_routes import template_router

configure_logging()
log = structlog.get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="Kynetic AI — Provisioning Service",
    description="Instance lifecycle management: launch, stop, terminate, SSH access.",
    version="0.4.0",
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

# Public API routes (proxied through gateway)
app.include_router(provisioning_router, prefix="/v1")
# Phase 6: Template registry + web UI token routes
app.include_router(template_router, prefix="/v1")

# Internal-only callback route (NOT proxied through gateway)
app.include_router(callback_router, prefix="/internal")


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok", "service": "provisioning_service"}


@app.on_event("startup")
async def on_startup():
    log.info(
        "provisioning_service.starting",
        environment=settings.environment,
        firecracker_mock=settings.firecracker_mock,
    )
