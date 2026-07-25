"""
Wallet & Billing Service — FastAPI application entry point.
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from libs.common.logging import configure_logging
from services.wallet_billing_service.config import get_settings
from services.wallet_billing_service.routes import billing_router, wallet_router

settings = get_settings()
configure_logging(log_level=settings.log_level)
logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Kynetic AI — Wallet & Billing Service",
    description="Developer wallets, dual-currency billing, and Stripe integration.",
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

app.include_router(wallet_router)
app.include_router(billing_router)


@app.on_event("startup")
async def on_startup():
    """Start Redis event listeners: wallet auto-create + billing lifecycle events."""
    # Existing: auto-create wallets on user signup
    from services.wallet_billing_service.event_listener import start_event_listener
    start_event_listener()

    # Phase 28: Billing lifecycle event loop (INSTANCE_RUNNING / TERMINATED / FAILED)
    from services.wallet_billing_service.event_handlers import start_billing_event_listeners
    app.state.billing_event_task = start_billing_event_listeners()

    logger.info("wallet_billing_service_started")


@app.get("/healthz", tags=["Health"])
async def health():
    return {"status": "ok", "service": "wallet_billing_service"}
