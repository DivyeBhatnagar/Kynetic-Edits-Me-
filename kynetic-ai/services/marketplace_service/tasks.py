"""
Marketplace Service — Celery tasks.

sync_availability_index:
  Runs every 5 min (Celery Beat). Queries all active listings
  from the DB, then atomically replaces the Redis availability
  set. This keeps the fast-browse cache in sync with heartbeat-
  driven host status changes from the host_service.
"""

import asyncio
from decimal import Decimal

import redis as sync_redis
import structlog
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from libs.db_models.marketplace_models import Listing, ListingStatus
from services.marketplace_service.celery_app import celery_app
from services.marketplace_service.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

AVAILABLE_KEY = "kynetic:listings:available"


def _get_sync_session() -> Session:
    """Synchronous session for Celery worker context."""
    # Use synchronous engine (workers don't run an asyncio event loop)
    sync_url = settings.database_url.replace("+asyncpg", "").replace("+aiosqlite", "")
    engine = create_engine(sync_url, pool_pre_ping=True)
    return Session(engine)


@celery_app.task(
    name="services.marketplace_service.tasks.sync_availability_index",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def sync_availability_index(self) -> dict:
    """
    Rebuild the Redis availability set from the current DB state.

    A listing is considered 'available' if:
      - status == 'active'
      - its host's last heartbeat is within the heartbeat_timeout threshold

    For MVP simplicity: we mark all 'active' listings as available.
    Phase 4 will tie in real heartbeat-based availability.
    """
    try:
        with _get_sync_session() as session:
            rows = session.execute(
                select(Listing.id).where(Listing.status == ListingStatus.active)
            ).scalars().all()

        available_ids = [str(lid) for lid in rows]

        r = sync_redis.from_url(settings.redis_url, decode_responses=True)
        pipe = r.pipeline(transaction=True)
        pipe.delete(AVAILABLE_KEY)
        if available_ids:
            pipe.sadd(AVAILABLE_KEY, *available_ids)
        pipe.execute()
        r.close()

        logger.info("availability_index_synced", count=len(available_ids))
        return {"synced_count": len(available_ids)}

    except Exception as exc:
        logger.error("sync_availability_index_failed", error=str(exc))
        raise self.retry(exc=exc)
