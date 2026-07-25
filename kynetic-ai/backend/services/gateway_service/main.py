"""
Gateway Service — FastAPI Application Entry Point
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from services.gateway_service.routes import gateway_router

app = FastAPI(
    title="Kynetic AI — Tunnel Gateway Service",
    description="Reverse-dial connection gateway and PTY terminal stream splicer.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(gateway_router)


@app.get("/healthz", tags=["Health"])
async def healthz():
    return {"status": "ok", "service": "gateway_service"}
