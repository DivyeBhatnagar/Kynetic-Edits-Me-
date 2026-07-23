"""
reputation_pricing_service — Celery app + Beat schedule.

Three periodic tasks:
  1. recompute_reputation    — triggered on job completion + hourly sweep
  2. train_pricing_model     — daily retrain as marketplace data accumulates
  3. predict_idle_time_batch — 6-hourly per-host idle prediction
"""

from celery import Celery
from celery.schedules import crontab

from services.reputation_pricing_service.config import get_settings

settings = get_settings()

celery_app = Celery(
    "reputation_pricing_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.reputation_pricing_service.tasks"],
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
    # Hourly sweep: recompute reputation for all hosts with job activity in last 24h
    "recompute-reputation-hourly": {
        "task": "services.reputation_pricing_service.tasks.recompute_reputation_sweep",
        "schedule": crontab(minute="0"),  # every hour on the hour
        "options": {"queue": "reputation"},
    },
    # Daily retrain of the pricing regression model
    "train-pricing-model-daily": {
        "task": "services.reputation_pricing_service.tasks.train_or_refresh_pricing_model",
        "schedule": crontab(hour="3", minute="0"),  # 3 AM UTC
        "options": {"queue": "ml"},
    },
    # 6-hourly idle prediction batch for all active hosts
    "predict-idle-time-6h": {
        "task": "services.reputation_pricing_service.tasks.predict_idle_time_batch",
        "schedule": crontab(minute="0", hour="*/6"),
        "options": {"queue": "reputation"},
    },
}
