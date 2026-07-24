"""
Wallet & Billing Service — Celery app.

Phase 28: Adds per-second billing metering tasks.
"""

from celery import Celery
from celery.schedules import crontab

from services.wallet_billing_service.config import get_settings

settings = get_settings()

celery_app = Celery(
    "wallet_billing_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "services.wallet_billing_service.tasks",
        # Phase 28: metering tasks (debit_running_instance, sweep_billing_meters)
        "services.wallet_billing_service.metering",
    ],
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

# Phase 28: Beat schedule — sweep for orphaned metering jobs every 60 seconds.
# This is the safety net for missed INSTANCE_RUNNING events (e.g., after worker restart).
celery_app.conf.beat_schedule = {
    "sweep-billing-meters-every-60s": {
        "task": "services.wallet_billing_service.tasks.sweep_billing_meters",
        "schedule": 60.0,  # every 60 seconds
    },
}

