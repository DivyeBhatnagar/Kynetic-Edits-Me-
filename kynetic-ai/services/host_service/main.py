"""Host Service — FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIDMiddleware
from services.host_service.config import get_settings
from services.host_service.routes import host_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(log_level=settings.log_level, is_production=settings.is_production)
    logger.info("host_service_startup", environment=settings.environment)
    yield
    logger.info("host_service_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Kynetic AI — Host Service",
        description="Host onboarding, hardware verification, benchmarking, and heartbeat ingestion.",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    app.include_router(host_router, prefix="/hosts", tags=["Hosts"])

    @app.get("/healthz", tags=["Health"])
    async def healthz():
        return {"status": "ok", "service": settings.service_name}

    return app


app = create_app()
