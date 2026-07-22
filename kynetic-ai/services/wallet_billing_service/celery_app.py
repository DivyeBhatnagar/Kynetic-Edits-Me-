"""
Wallet & Billing Service — Celery app.

Currently stubs the Celery app for worker startup.
Phase 4 will add the per-second billing tick task here.
"""

from celery import Celery

from services.wallet_billing_service.config import get_settings

settings = get_settings()

celery_app = Celery(
    "wallet_billing_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.wallet_billing_service.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

# Phase 4: Beat schedule will add per-second billing tick here
celery_app.conf.beat_schedule = {}
