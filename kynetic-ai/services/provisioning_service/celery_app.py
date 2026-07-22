"""
Provisioning Service — Celery Application.

Beat schedule:
  reconcile_billing — runs every 60 seconds to restart billing watchers
  after worker restarts.
"""

from celery import Celery

from services.provisioning_service.config import get_settings

settings = get_settings()

celery_app = Celery(
    "provisioning_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.provisioning_service.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,           # re-queue on worker crash
    worker_prefetch_multiplier=1,  # fair dispatch for long-running tasks
    # Beat schedule — reconciliation sweep every 60 seconds
    beat_schedule={
        "reconcile-billing-every-60s": {
            "task": "reconcile_billing",
            "schedule": 60.0,
        },
    },
)
