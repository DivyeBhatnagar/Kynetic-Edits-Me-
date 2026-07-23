"""
Notifications Service — FastAPI application.

Port: 8010 (internal only, behind API Gateway)
"""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.notifications_service.routes import notifications_router, support_router

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Kynetic Notifications Service",
    description="Event-driven notifications and support ticket routing.",
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

app.include_router(notifications_router)
app.include_router(support_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "notifications_service"}
