"""
Phase 28 — Internal Event Bus (libs/events/bus.py)

Lightweight Redis pub/sub event bus for cross-service lifecycle events.
All event types are typed string constants — no magic strings anywhere.

Architecture:
  Provisioning Service (publisher)  →  Redis pub/sub  →  Billing Service (subscriber)
"""

from __future__ import annotations

import json
import structlog
from typing import AsyncGenerator

import redis.asyncio as aioredis

log = structlog.get_logger(__name__)

# ── Event type constants ──────────────────────────────────────────────────────

INSTANCE_RUNNING    = "instance.running"     # instance transitioned to running
INSTANCE_TERMINATED = "instance.terminated"  # instance terminated or failed
INSTANCE_FAILED     = "instance.failed"      # unrecoverable provisioning failure

#: All channels this bus cares about. Used by multi-channel subscriber.
ALL_INSTANCE_CHANNELS = (INSTANCE_RUNNING, INSTANCE_TERMINATED, INSTANCE_FAILED)

# ── Redis connection (lazy, module-level singleton) ───────────────────────────

_redis_client: aioredis.Redis | None = None


def _get_redis(redis_url: str = "redis://redis:6379/3") -> aioredis.Redis:
    """
    Return a module-level Redis client, creating it on first call.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(redis_url, decode_responses=True)
    return _redis_client


def configure_bus(redis_url: str) -> None:
    """
    Override the default Redis URL (called from service startup).
    """
    global _redis_client
    _redis_client = aioredis.from_url(redis_url, decode_responses=True)


# ── Publisher ─────────────────────────────────────────────────────────────────

async def publish_event(event_type: str, payload: dict) -> None:
    """
    Publish a lifecycle event to all subscribers.
    """
    try:
        r = _get_redis()
        data = json.dumps(payload)
        receivers = await r.publish(event_type, data)
        log.info(
            "event_bus.published",
            event_type=event_type,
            receivers=receivers,
            instance_id=payload.get("instance_id"),
        )
    except Exception as exc:
        log.error(
            "event_bus.publish_failed",
            event_type=event_type,
            error=str(exc),
            instance_id=payload.get("instance_id"),
        )


# ── Subscriber ────────────────────────────────────────────────────────────────

async def subscribe(event_type: str) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields decoded event payloads from a single channel.
    """
    r = _get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(event_type)
    log.info("event_bus.subscribed", channel=event_type)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                yield json.loads(message["data"])
            except json.JSONDecodeError as exc:
                log.warning(
                    "event_bus.bad_payload",
                    channel=event_type,
                    error=str(exc),
                    raw=message["data"][:200],
                )
    finally:
        await pubsub.unsubscribe(event_type)
        log.info("event_bus.unsubscribed", channel=event_type)


async def subscribe_many(
    *event_types: str,
) -> AsyncGenerator[tuple[str, dict], None]:
    """
    Async generator that listens on multiple channels simultaneously.
    Yields (event_type, payload) tuples.
    """
    r = _get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe(*event_types)
    log.info("event_bus.subscribed_many", channels=list(event_types))

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            channel = message["channel"]
            try:
                yield channel, json.loads(message["data"])
            except json.JSONDecodeError as exc:
                log.warning(
                    "event_bus.bad_payload",
                    channel=channel,
                    error=str(exc),
                )
    finally:
        await pubsub.unsubscribe(*event_types)
        log.info("event_bus.unsubscribed_many", channels=list(event_types))
