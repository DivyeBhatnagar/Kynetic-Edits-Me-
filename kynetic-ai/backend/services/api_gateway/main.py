"""
API Gateway — FastAPI entry point for all Kynetic AI services.

Responsibilities:
- JWT validation on all protected routes (before proxying)
- Global rate limiting (Redis-backed token bucket)
- Request routing to internal services
- Unified OpenAPI docs (aggregated from all services)
- Health check aggregation
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from libs.common.middleware import CorrelationIDMiddleware
from services.api_gateway.config import get_settings
from services.api_gateway.rate_limiter import RateLimitConfig, RateLimiterMiddleware
from services.api_gateway.routes import gateway_router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(log_level=settings.log_level, is_production=settings.is_production)
    logger.info("api_gateway_startup", environment=settings.environment)
    yield
    logger.info("api_gateway_shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Kynetic AI — API Gateway",
        description="Unified entry point: auth check, rate limiting, routing to internal services.",
        version="1.0.0",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # Middleware (outermost first)
    app.add_middleware(CorrelationIDMiddleware)
    app.add_middleware(
        RateLimiterMiddleware,
        config=RateLimitConfig(
            redis_url=settings.redis_url,
            default_rpm=settings.rate_limit_rpm if hasattr(settings, "rate_limit_rpm") else 60,
            burst=10,
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(gateway_router)

    @app.get("/healthz", tags=["Health"])
    async def healthz():
        return {"status": "ok", "service": "api_gateway"}

    return app


app = create_app()
