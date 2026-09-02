"""
Kynetic AI Common — Celery Application Factory (libs/common/celery_factory.py)

Provides a standardized, robust Celery app constructor with sensible defaults
(JSON serialization, UTC timezone, late task acks, fair prefetch multiplier).
Used by all microservices to eliminate Celery setup boilerplate.
"""

from __future__ import annotations

from typing import Any
from celery import Celery


def create_celery_app(
    service_name: str,
    broker_url: str,
    result_backend: str,
    include_tasks: list[str],
    beat_schedule: dict[str, Any] | None = None,
) -> Celery:
    """
    Constructs and configures a standard Kynetic Celery application instance.

    Args:
        service_name: Name of the microservice (e.g. 'provisioning_service')
        broker_url: Redis/RabbitMQ broker URL
        result_backend: Celery result backend URL
        include_tasks: List of task module import strings
        beat_schedule: Optional beat schedule dict
    """
    app = Celery(
        service_name,
        broker=broker_url,
        backend=result_backend,
        include=include_tasks,
    )

    conf: dict[str, Any] = {
        "task_serializer": "json",
        "result_serializer": "json",
        "accept_content": ["json"],
        "timezone": "UTC",
        "enable_utc": True,
        "task_acks_late": True,
        "worker_prefetch_multiplier": 1,
    }

    if beat_schedule:
        conf["beat_schedule"] = beat_schedule

    app.conf.update(**conf)
    return app
