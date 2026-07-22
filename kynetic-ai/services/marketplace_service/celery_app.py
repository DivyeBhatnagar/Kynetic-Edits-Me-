"""
Marketplace Service — Celery app + Beat schedule.
"""

from celery import Celery
from celery.schedules import crontab

from services.marketplace_service.config import get_settings

settings = get_settings()

celery_app = Celery(
    "marketplace_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.marketplace_service.tasks"],
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

celery_app.conf.beat_schedule = {
    # Sync Redis availability index from DB every 5 minutes
    "sync-availability-index": {
        "task": "services.marketplace_service.tasks.sync_availability_index",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "celery"},
    },
}
