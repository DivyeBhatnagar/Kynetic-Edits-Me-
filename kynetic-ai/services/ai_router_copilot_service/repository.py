"""
AI Router & Copilot Service — Database Repository.

Handles:
  - Fetching active listings with benchmark scores (for the Router ranking)
  - Persisting RouterRecommendation audit rows
  - CopilotSession create/fetch
  - CopilotMessage append/fetch
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.router_copilot_models import (
    CopilotMessage,
    CopilotSession,
    MessageRole,
    RouterRecommendation,
)

log = structlog.get_logger(__name__)


# ── Listings query (cross-service read via shared DB) ─────────────────────────

LISTINGS_WITH_BENCHMARKS_SQL = text("""
    SELECT
        l.id,
        l.host_id,
        l.title,
        l.gpu_model,
        l.gpu_count,
        l.gpu_vram_gb::float,
        l.cpu_cores,
        l.ram_gb::float,
        l.region,
        l.price_per_hour_usd::float,
        l.price_per_hour_inr::float,
        l.benchmark_scores,
        -- Latest benchmark score for this host (prefer LLM_INFERENCE if available)
        (
            SELECT hb.score
            FROM host_benchmarks hb
            WHERE hb.host_id = l.host_id
            ORDER BY
                CASE hb.benchmark_type
                    WHEN 'llm_inference' THEN 1
                    WHEN 'flops' THEN 2
                    WHEN 'image_gen' THEN 3
                END,
                hb.run_at DESC
            LIMIT 1
        ) AS benchmark_score,
        (
            SELECT hb.benchmark_type
            FROM host_benchmarks hb
            WHERE hb.host_id = l.host_id
            ORDER BY
                CASE hb.benchmark_type
                    WHEN 'llm_inference' THEN 1
                    WHEN 'flops' THEN 2
                    WHEN 'image_gen' THEN 3
                END,
                hb.run_at DESC
            LIMIT 1
        ) AS benchmark_type,
        -- Availability: host's last heartbeat within 5 min AND status != busy
        (
            SELECT
                CASE
                    WHEN hh.status IN ('idle') AND hh.recorded_at > NOW() - INTERVAL '5 minutes'
                    THEN true
                    ELSE false
                END
            FROM host_heartbeats hh
            WHERE hh.host_id = l.host_id
            ORDER BY hh.recorded_at DESC
            LIMIT 1
        ) AS is_available
    FROM listings l
    WHERE
        l.status = 'active'
        {gpu_filter}
        {region_filter}
""")


async def fetch_active_listings(
    session: AsyncSession,
    *,
    min_gpu_vram_gb: float | None = None,
    region: str | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch all active listings enriched with benchmark scores and availability.

    Uses raw SQL to avoid N+1 problems; returns plain dicts for the
    ranking function (no ORM dependency in ranking.py).
    """
    gpu_filter = ""
    region_filter = ""

    if min_gpu_vram_gb is not None:
        gpu_filter = f"AND l.gpu_vram_gb >= {float(min_gpu_vram_gb)}"
    if region is not None:
        # Parameterised inline for the raw-text query; value is validated upstream.
        safe_region = region.replace("'", "''")
        region_filter = f"AND l.region = '{safe_region}'"

    sql_str = LISTINGS_WITH_BENCHMARKS_SQL.text.format(
        gpu_filter=gpu_filter, region_filter=region_filter
    )

    result = await session.execute(text(sql_str))
    rows = result.mappings().all()
    listings = [dict(r) for r in rows]
    log.info("repository.listings_fetched", count=len(listings))
    return listings


# ── RouterRecommendation ──────────────────────────────────────────────────────

async def save_recommendation(
    session: AsyncSession,
    *,
    developer_id: uuid.UUID | None,
    request_payload: dict[str, Any],
    recommended_listing_ids: list[str],
    ranked_results: list[dict[str, Any]],
) -> RouterRecommendation:
    rec = RouterRecommendation(
        developer_id=developer_id,
        request_payload=request_payload,
        recommended_listing_ids=recommended_listing_ids,
        ranked_results=ranked_results,
    )
    session.add(rec)
    await session.flush()
    await session.refresh(rec)
    return rec


# ── CopilotSession ────────────────────────────────────────────────────────────

async def get_or_create_session(
    session: AsyncSession,
    *,
    session_id: uuid.UUID | None,
    developer_id: uuid.UUID | None,
) -> CopilotSession:
    if session_id is not None:
        result = await session.execute(
            select(CopilotSession).where(CopilotSession.id == session_id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

    new_session = CopilotSession(developer_id=developer_id)
    session.add(new_session)
    await session.flush()
    await session.refresh(new_session)
    log.info("copilot.session_created", session_id=str(new_session.id))
    return new_session


async def get_session_with_messages(
    session: AsyncSession,
    session_id: uuid.UUID,
) -> CopilotSession | None:
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(CopilotSession)
        .where(CopilotSession.id == session_id)
        .options(selectinload(CopilotSession.messages))
    )
    return result.scalar_one_or_none()


# ── CopilotMessage ────────────────────────────────────────────────────────────

async def append_message(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    role: MessageRole,
    content: str,
    router_recommendation_id: uuid.UUID | None = None,
) -> CopilotMessage:
    msg = CopilotMessage(
        session_id=session_id,
        role=role,
        content=content,
        router_recommendation_id=router_recommendation_id,
    )
    session.add(msg)
    await session.flush()
    await session.refresh(msg)
    return msg


async def get_recent_messages(
    session: AsyncSession,
    session_id: uuid.UUID,
    *,
    limit: int = 20,
) -> list[CopilotMessage]:
    """Fetch the most recent `limit` messages for LangChain memory reconstruction."""
    result = await session.execute(
        select(CopilotMessage)
        .where(CopilotMessage.session_id == session_id)
        .order_by(CopilotMessage.created_at.asc())
        .limit(limit)
    )
    return list(result.scalars().all())
