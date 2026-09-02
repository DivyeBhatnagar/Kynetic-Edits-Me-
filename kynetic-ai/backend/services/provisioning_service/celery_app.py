"""
Provisioning Service — Celery Application.

Beat schedule:
  reconcile_billing — runs every 60 seconds to restart billing watchers
  after worker restarts.
"""

from libs.common.celery_factory import create_celery_app
from services.provisioning_service.config import get_settings

settings = get_settings()

celery_app = create_celery_app(
    service_name="provisioning_service",
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    include_tasks=["services.provisioning_service.tasks"],
    beat_schedule={
        "reconcile-billing-every-60s": {
            "task": "reconcile_billing",
            "schedule": 60.0,
        },
    },
)
