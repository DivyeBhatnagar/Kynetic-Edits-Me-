"""
Marketplace Service — Redis availability index.

Maintains a live set of available listing IDs:
  kynetic:listings:available  → Redis SET of listing UUID strings

Operations:
  mark_available(listing_id)    → SADD
  mark_unavailable(listing_id)  → SREM
  is_available(listing_id)      → SISMEMBER
  get_available_ids()           → SMEMBERS
  bulk_sync(available_ids)      → atomic replace via pipeline

The availability state is derived from:
  1. Listing status == 'active'
  2. The host's most recent heartbeat was within HEARTBEAT_TIMEOUT_SECONDS
  3. The host is not suspended or flagged

This module is called from:
  - routes.py (on listing create/update/delete)
  - tasks.py (periodic Celery Beat sync every 5 min)
"""

import uuid
from typing import Iterable

import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger(__name__)

AVAILABLE_KEY = "kynetic:listings:available"


def _get_client(redis_url: str) -> aioredis.Redis:
    return aioredis.from_url(redis_url, decode_responses=True)


async def mark_available(redis_url: str, listing_id: uuid.UUID) -> None:
    async with _get_client(redis_url) as r:
        await r.sadd(AVAILABLE_KEY, str(listing_id))
    logger.debug("listing_marked_available", listing_id=str(listing_id))


async def mark_unavailable(redis_url: str, listing_id: uuid.UUID) -> None:
    async with _get_client(redis_url) as r:
        await r.srem(AVAILABLE_KEY, str(listing_id))
    logger.debug("listing_marked_unavailable", listing_id=str(listing_id))


async def is_available(redis_url: str, listing_id: uuid.UUID) -> bool:
    async with _get_client(redis_url) as r:
        return bool(await r.sismember(AVAILABLE_KEY, str(listing_id)))


async def get_available_ids(redis_url: str) -> set[str]:
    async with _get_client(redis_url) as r:
        return await r.smembers(AVAILABLE_KEY)


async def bulk_sync(redis_url: str, available_ids: Iterable[uuid.UUID]) -> int:
    """
    Atomically replace the available set with the provided IDs.
    Returns the new count.
    """
    str_ids = [str(lid) for lid in available_ids]
    async with _get_client(redis_url) as r:
        pipe = r.pipeline(transaction=True)
        pipe.delete(AVAILABLE_KEY)
        if str_ids:
            pipe.sadd(AVAILABLE_KEY, *str_ids)
        await pipe.execute()

    count = len(str_ids)
    logger.info("availability_index_synced", available_count=count)
    return count


async def enrich_with_availability(
    redis_url: str, listings: list
) -> list:
    """
    Inject `is_available` bool into a list of listing objects/dicts.
    Single Redis call using SMEMBERS (efficient for up to ~100k listings).
    """
    available = await get_available_ids(redis_url)
    for listing in listings:
        lid = str(listing.id) if hasattr(listing, "id") else str(listing.get("id", ""))
        listing.is_available = lid in available
    return listings
