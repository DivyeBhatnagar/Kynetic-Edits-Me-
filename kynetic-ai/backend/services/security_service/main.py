"""
Security Service — FastAPI entry point.
Port: 8006
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from services.security_service.config import get_settings
from services.security_service.routes import router

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(log_level=settings.log_level, is_production=settings.is_production)
    log.info("security_service.startup", environment=settings.environment)
    yield
    log.info("security_service.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Kynetic AI — Security Service",
        description="Security hardening: kill switch, image scanning, trust tiers, audit logs.",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Internal service — handled by gateway
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    @app.get("/health", tags=["Health"])
    async def health():
        return {"status": "ok", "service": "security_service"}

    return app


app = create_app()
