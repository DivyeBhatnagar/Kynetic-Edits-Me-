"""
Security Service — Celery App.
"""

from celery.schedules import crontab
from libs.common.celery_factory import create_celery_app
from services.security_service.config import get_settings

settings = get_settings()

celery_app = create_celery_app(
    service_name="security_service",
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    include_tasks=["services.security_service.tasks"],
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
