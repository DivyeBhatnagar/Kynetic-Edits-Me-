"""
Security Service — Celery App.
"""

from celery import Celery
from celery.schedules import crontab

from services.security_service.config import get_settings

settings = get_settings()

celery_app = Celery(
    "security_service",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["services.security_service.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # Scan wallet transactions for fraud patterns every 5 minutes
        "fraud-rule-scan": {
            "task": "services.security_service.tasks.fraud_rule_scan_all",
            "schedule": crontab(minute="*/5"),
        },
        # Check for stale un-terminated instances that might be abusing resources
        "resource-abuse-check": {
            "task": "services.security_service.tasks.resource_abuse_sweep",
            "schedule": crontab(minute="*/15"),
        },
    },
)
