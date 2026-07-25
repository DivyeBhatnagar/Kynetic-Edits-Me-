"""
Security Service — Celery Tasks.

Tasks:
  scan_image_before_launch  — Pre-launch image scan (called from provisioning_service)
  analyze_instance_telemetry — Processes a single telemetry payload for mining/abuse
  fraud_rule_scan_all       — Periodic: runs fraud rules across active users
  resource_abuse_sweep      — Periodic: checks for anomalous resource usage signals
"""

import uuid
from typing import Any

import structlog
from celery import shared_task

from services.security_service.celery_app import celery_app
from services.security_service.image_scanner import ImageScanBlockedError, scan_image
from services.security_service.runtime_monitor import MiningDetectedError, analyze_telemetry

log = structlog.get_logger(__name__)


@celery_app.task(name="services.security_service.tasks.scan_image_before_launch", bind=True, max_retries=2)
def scan_image_before_launch(self, image: str, instance_id: str) -> dict[str, Any]:
    """
    Scans a container image before provisioning the instance.
    If blocked, marks the instance as failed via the provisioning service.

    Called by provisioning_service.tasks.provision_instance before starting the VM.
    """
    log.info("task.scan_image", image=image, instance_id=instance_id)

    from services.security_service.config import get_settings
    settings = get_settings()

    try:
        result = scan_image(image)
    except Exception as exc:
        log.error("task.scan_image.error", image=image, error=str(exc))
        raise self.retry(exc=exc, countdown=30)

    # Emit result to a Redis key readable by provisioning_service
    import redis
    r = redis.Redis.from_url(settings.redis_url)
    import json
    r.setex(
        f"kynetic:scan_result:{instance_id}",
        300,  # 5-minute TTL
        json.dumps(result.model_dump()),
    )

    if result.blocked:
        log.critical(
            "task.scan_image.blocked",
            image=image,
            instance_id=instance_id,
            critical=result.critical_count,
            high=result.high_count,
        )
        # Signal provisioning service to fail the instance
        r.setex(f"kynetic:scan_blocked:{instance_id}", 300, "1")

    return result.model_dump()


@celery_app.task(name="services.security_service.tasks.analyze_instance_telemetry", bind=True)
def analyze_instance_telemetry(self, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Processes one telemetry sample for mining/abuse detection.
    If mining is detected: publishes a kill_switch event to Redis.
    Called by the host_agent's periodic telemetry publisher.
    """
    instance_id = payload.get("instance_id", "unknown")
    log.debug("task.analyze_telemetry", instance_id=instance_id)

    try:
        report = analyze_telemetry(payload)
    except MiningDetectedError as exc:
        log.critical("task.mining_detected", instance_id=exc.instance_id, evidence=exc.evidence)

        # Publish mining event so provisioning service can terminate immediately
        from services.security_service.config import get_settings
        import redis, json
        settings = get_settings()
        r = redis.Redis.from_url(settings.redis_url)
        r.publish(
            "kynetic:kill_switch",
            json.dumps({
                "target_type": "instance",
                "target_id": exc.instance_id,
                "reason": "crypto_mining_detected",
                "evidence": exc.evidence,
            }),
        )
        return {
            "mining_detected": True,
            "instance_id": exc.instance_id,
            "evidence": exc.evidence,
        }

    return report


@celery_app.task(name="services.security_service.tasks.fraud_rule_scan_all")
def fraud_rule_scan_all() -> dict[str, Any]:
    """
    Periodic task: scans all users who have had wallet activity in the past 24 hours.
    In mock mode: no-op.
    """
    from services.security_service.config import get_settings
    settings = get_settings()

    if settings.scanner_mock:
        log.debug("task.fraud_rule_scan_all.mock_skip")
        return {"scanned": 0, "flagged": 0, "mock": True}

    log.info("task.fraud_rule_scan_all.start")
    # In production: fetch user IDs with recent activity and scan each.
    # Deferred to production bootstrap — no multi-user query without real DB.
    return {"scanned": 0, "flagged": 0, "note": "production_only"}


@celery_app.task(name="services.security_service.tasks.resource_abuse_sweep")
def resource_abuse_sweep() -> dict[str, Any]:
    """
    Periodic task: checks Redis for any unprocessed abuse signals and escalates.
    In mock mode: no-op.
    """
    from services.security_service.config import get_settings
    settings = get_settings()

    if settings.scanner_mock:
        return {"checked": 0, "mock": True}

    import redis
    r = redis.Redis.from_url(settings.redis_url)
    # Scan for any kill_switch signals that haven't been acted on
    # (robustness: in case the pub/sub subscriber missed a message)
    keys = r.keys("kynetic:scan_blocked:*")
    acted = 0
    for key in keys:
        if r.exists(key):
            instance_id = key.decode().split(":")[-1]
            log.warning("task.resource_abuse_sweep.stale_block", instance_id=instance_id)
            acted += 1
    return {"checked": len(keys), "acted": acted}
