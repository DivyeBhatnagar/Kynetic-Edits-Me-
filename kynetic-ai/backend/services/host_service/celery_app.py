"""
Host Service — Celery app + background tasks.

Phase 2 background jobs:
1. process_heartbeat      — Async Celery task to handle high-volume heartbeat ingestion
2. trigger_rebenchmark    — Sends re-benchmark signal to a specific host agent
3. rebenchmark_sweep      — Celery Beat periodic task: find all stale hosts and enqueue re-benchmarks
4. mark_offline_sweep     — Celery Beat periodic task: mark hosts offline if heartbeat exceeds timeout

Celery Beat schedule is configured here and picked up by the Celery Beat worker.
"""

from celery import Celery
from celery.schedules import crontab

from libs.common.logging import configure_logging
from services.host_service.config import get_settings

settings = get_settings()
configure_logging(log_level=settings.log_level, is_production=settings.is_production)

# ---------------------------------------------------------------------------
# Celery application
# ---------------------------------------------------------------------------
celery_app = Celery(
    "host_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.host_service.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,         # Ack after task completes — requeue on crash
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task per worker at a time for fair distribution
)

# ---------------------------------------------------------------------------
# Celery Beat Schedule
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    # Every 10 minutes: mark hosts that haven't heartbeat-ed as offline
    "mark-offline-sweep": {
        "task": "services.host_service.tasks.mark_offline_sweep",
        "schedule": crontab(minute="*/10"),
        "options": {"expires": 300},  # Don't run if overdue by >5 min
    },
    # Every hour: find verified hosts whose benchmarks are stale and trigger re-run
    "rebenchmark-sweep": {
        "task": "services.host_service.tasks.rebenchmark_sweep",
        "schedule": crontab(minute=0),  # Top of every hour
        "options": {"expires": 3600},
    },
}
