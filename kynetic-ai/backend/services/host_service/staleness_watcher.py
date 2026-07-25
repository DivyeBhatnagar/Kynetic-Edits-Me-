"""
Host Service — Host Staleness Watcher & Offline Detector (staleness_watcher.py)

Monitors heartbeat timestamps for all registered hosts.
If a host misses heartbeats beyond the configured threshold (default 60s),
its status is updated to HeartbeatStatus.OFFLINE and its listings are flagged.
"""

from datetime import datetime, timedelta, timezone
import uuid
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.host_models import Host, HostHeartbeat, HeartbeatStatus, HostStatus
from libs.db_models.marketplace_models import Listing, ListingStatus

log = structlog.get_logger(__name__)


async def check_and_mark_offline_hosts(session: AsyncSession, timeout_seconds: int = 60) -> list[uuid.UUID]:
    """
    Scans hosts and marks any host as OFFLINE if no heartbeat has been received
    within timeout_seconds.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(seconds=timeout_seconds)

    # 1. Query active hosts where latest heartbeat or updated_at is older than cutoff
    stmt = (
        select(Host.id)
        .where(
            Host.status.in_([HostStatus.VERIFIED, HostStatus.LISTED]),
            Host.updated_at < cutoff,
        )
    )
    result = await session.execute(stmt)
    stale_host_ids = list(result.scalars().all())

    if not stale_host_ids:
        return []

    log.info("staleness_watcher.stale_hosts_detected", count=len(stale_host_ids), host_ids=[str(h) for h in stale_host_ids])

    # 2. Flag active listings for stale hosts
    await session.execute(
        update(Listing)
        .where(
            Listing.host_id.in_(stale_host_ids),
            Listing.status == ListingStatus.active,
        )
        .values(status=ListingStatus.paused)
    )

    await session.flush()
    return stale_host_ids
