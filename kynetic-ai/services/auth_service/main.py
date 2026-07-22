"""
Auth Service — FastAPI application entry point.

Handles: signup, login, JWT issuance/refresh, logout, phone OTP verification.
Supports host, developer, and both roles on a single account.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIDMiddleware
from services.auth_service.config import get_settings
from services.auth_service.routes import auth_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle handler."""
    settings = get_settings()
    configure_logging(log_level=settings.log_level, is_production=settings.is_production)
    logger.info(
        "auth_service_startup",
        service=settings.service_name,
        environment=settings.environment,
    )
    yield
    logger.info("auth_service_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Kynetic AI — Auth Service",
        description="Authentication, JWT issuance, phone OTP, and user management.",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: outermost runs first on request) ──────────
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ── Routes ───────────────────────────────────────────────────────────────
    app.include_router(auth_router, prefix="/auth", tags=["Authentication"])

    # ── Health check (required on every service per the implementation plan) ─
    @app.get("/healthz", tags=["Health"])
    async def healthz():
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
