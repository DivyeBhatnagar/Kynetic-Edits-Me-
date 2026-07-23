"""
Marketplace Service — Redis availability index.
# ponytail: direct Redis set operations (saved 50 lines)
"""

import uuid
from typing import Iterable
import redis.asyncio as aioredis

AVAILABLE_KEY = "kynetic:listings:available"


async def mark_available(redis_url: str, listing_id: uuid.UUID) -> None:
    async with aioredis.from_url(redis_url, decode_responses=True) as r:
        await r.sadd(AVAILABLE_KEY, str(listing_id))


async def mark_unavailable(redis_url: str, listing_id: uuid.UUID) -> None:
    async with aioredis.from_url(redis_url, decode_responses=True) as r:
        await r.srem(AVAILABLE_KEY, str(listing_id))


async def is_available(redis_url: str, listing_id: uuid.UUID) -> bool:
    async with aioredis.from_url(redis_url, decode_responses=True) as r:
        return bool(await r.sismember(AVAILABLE_KEY, str(listing_id)))


async def get_available_ids(redis_url: str) -> set[str]:
    async with aioredis.from_url(redis_url, decode_responses=True) as r:
        return await r.smembers(AVAILABLE_KEY)


async def bulk_sync(redis_url: str, available_ids: Iterable[uuid.UUID]) -> int:
    str_ids = [str(lid) for lid in available_ids]
    async with aioredis.from_url(redis_url, decode_responses=True) as r:
        pipe = r.pipeline(transaction=True)
        pipe.delete(AVAILABLE_KEY)
        if str_ids:
            pipe.sadd(AVAILABLE_KEY, *str_ids)
        await pipe.execute()
    return len(str_ids)


async def enrich_with_availability(redis_url: str, listings: list) -> list:
    available = await get_available_ids(redis_url)
    for listing in listings:
        lid = str(getattr(listing, "id", listing.get("id", "") if isinstance(listing, dict) else ""))
        setattr(listing, "is_available", lid in available)
    return listings
