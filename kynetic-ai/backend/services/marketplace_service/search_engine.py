"""
Services/marketplace_service/search_engine.py
v8 Feature 5 — Smart Search Engine.

Implements:
1. Event-driven denormalized listing sync (sync_searchable_listing, sync_all_searchable_listings)
2. Multi-attribute composable search engine (execute_smart_search)
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.host_models import Host
from libs.db_models.marketplace_models import Listing, SearchableListing
from libs.db_models.reputation_pricing_models import HostScore, ReputationScore


async def sync_searchable_listing(
    session: AsyncSession,
    listing_id: uuid.UUID,
) -> SearchableListing | None:
    """Sync or upsert a single listing into searchable_listings with 1 query."""
    stmt = select(Listing, Host).outerjoin(Host, Listing.host_id == Host.id).where(Listing.id == listing_id)
    res = await session.execute(stmt)
    row = res.first()
    if not row:
        return None
    listing, host = row
    
    hs_res = await session.execute(select(HostScore).where(HostScore.host_id == listing.host_id).order_by(HostScore.computed_at.desc()).limit(1))
    host_score = hs_res.scalars().first()
    rs_res = await session.execute(select(ReputationScore).where(ReputationScore.host_id == listing.host_id).order_by(ReputationScore.computed_at.desc()).limit(1))
    rep_score = rs_res.scalars().first()

    # Build search values
    now = datetime.now(UTC)
    gpu_model = listing.gpu_model
    vram_gb = float(listing.gpu_vram_gb) if listing.gpu_vram_gb is not None else None
    price_usd = listing.price_per_hour_usd
    price_inr = listing.price_per_hour_inr
    region = listing.region or "us-east"

    perf_score = float(host_score.performance_score) if host_score and host_score.performance_score is not None else 0.50
    health_score = float(host_score.health_score) if host_score and host_score.health_score is not None else 0.80
    fp16_tflops = float(host_score.fp16_tflops_normalised * 100.0) if host_score and host_score.fp16_tflops_normalised is not None else None
    rep_composite = float(rep_score.composite_score) if rep_score else 0.50

    verif_level = host.verification_level if host else "unverified"
    os_type = host.os_type.value if host else "linux"
    avail_status = listing.status.value if listing.status else "active"

    # Upsert row
    sl_stmt = select(SearchableListing).where(SearchableListing.listing_id == listing_id)
    sl_res = await session.execute(sl_stmt)
    row = sl_res.scalars().first()

    if not row:
        row = SearchableListing(
            listing_id=listing_id,
            host_id=listing.host_id,
            gpu_model=gpu_model,
            vram_gb=vram_gb,
            tensor_fp16_tflops=fp16_tflops,
            performance_score=perf_score,
            health_score=health_score,
            reputation_composite_score=rep_composite,
            verification_level=verif_level,
            price_per_hour_usd=price_usd,
            price_per_hour_inr=price_inr,
            region=region,
            cpu_cores=listing.cpu_cores,
            ram_gb=float(listing.ram_gb) if listing.ram_gb is not None else None,
            storage_gb=float(listing.storage_gb) if listing.storage_gb is not None else None,
            os_type=os_type,
            availability_status=avail_status,
            created_at=listing.created_at or now,
            updated_at=now,
        )
        session.add(row)
    else:
        row.gpu_model = gpu_model
        row.vram_gb = vram_gb
        row.tensor_fp16_tflops = fp16_tflops
        row.performance_score = perf_score
        row.health_score = health_score
        row.reputation_composite_score = rep_composite
        row.verification_level = verif_level
        row.price_per_hour_usd = price_usd
        row.price_per_hour_inr = price_inr
        row.region = region
        row.cpu_cores = listing.cpu_cores
        row.ram_gb = float(listing.ram_gb) if listing.ram_gb is not None else None
        row.storage_gb = float(listing.storage_gb) if listing.storage_gb is not None else None
        row.os_type = os_type
        row.availability_status = avail_status
        row.updated_at = now

    await session.flush()
    return row


async def sync_all_searchable_listings(session: AsyncSession) -> int:
    """
    Refresh all active listings into searchable_listings.
    """
    stmt = select(Listing.id)
    res = await session.execute(stmt)
    listing_ids = res.scalars().all()

    count = 0
    for lid in listing_ids:
        await sync_searchable_listing(session, lid)
        count += 1
    return count


async def execute_smart_search(
    session: AsyncSession,
    filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Multi-attribute composable search engine query over searchable_listings.
    """
    stmt = select(SearchableListing)

    # 1. Hard filter constraints
    if filters.get("gpu_model"):
        stmt = stmt.where(func.lower(SearchableListing.gpu_model) == func.lower(filters["gpu_model"]))
    if filters.get("min_vram"):
        stmt = stmt.where(SearchableListing.vram_gb >= float(filters["min_vram"]))
    if filters.get("min_tensor_perf"):
        stmt = stmt.where(SearchableListing.tensor_fp16_tflops >= float(filters["min_tensor_perf"]))
    if filters.get("min_health_score"):
        stmt = stmt.where(SearchableListing.health_score >= float(filters["min_health_score"]))
    if filters.get("min_reputation"):
        stmt = stmt.where(SearchableListing.reputation_composite_score >= float(filters["min_reputation"]))
    if filters.get("verification_level"):
        stmt = stmt.where(func.lower(SearchableListing.verification_level) == func.lower(filters["verification_level"]))
    if filters.get("max_price"):
        stmt = stmt.where(SearchableListing.price_per_hour_usd <= Decimal(str(filters["max_price"])))
    if filters.get("region"):
        stmt = stmt.where(func.lower(SearchableListing.region) == func.lower(filters["region"]))
    if filters.get("min_cpu_cores"):
        stmt = stmt.where(SearchableListing.cpu_cores >= int(filters["min_cpu_cores"]))
    if filters.get("min_ram_gb"):
        stmt = stmt.where(SearchableListing.ram_gb >= float(filters["min_ram_gb"]))
    if filters.get("os"):
        stmt = stmt.where(func.lower(SearchableListing.os_type) == func.lower(filters["os"]))

    # Filter out inactive unless explicitly requested
    if not filters.get("include_inactive"):
        stmt = stmt.where(SearchableListing.availability_status == "active")

    # 2. Ranking / Sorting
    sort_key = (filters.get("sort") or "value").lower()
    if sort_key == "price":
        stmt = stmt.order_by(SearchableListing.price_per_hour_usd.asc())
    elif sort_key in ("performance", "fastest"):
        stmt = stmt.order_by(SearchableListing.performance_score.desc())
    elif sort_key == "reputation":
        stmt = stmt.order_by(SearchableListing.reputation_composite_score.desc())
    elif sort_key == "newest":
        stmt = stmt.order_by(SearchableListing.created_at.desc())
    else:  # "value" default: performance_score / price_per_hour_usd
        stmt = stmt.order_by(
            (SearchableListing.performance_score / SearchableListing.price_per_hour_usd).desc()
        )

    # 3. Pagination
    offset = int(filters.get("offset") or 0)
    limit = int(filters.get("limit") or 20)
    stmt = stmt.offset(offset).limit(limit)

    res = await session.execute(stmt)
    scalars = res.scalars().all()

    return [
        {
            "listing_id": str(r.listing_id),
            "host_id": str(r.host_id),
            "gpu_model": r.gpu_model,
            "vram_gb": float(r.vram_gb) if r.vram_gb is not None else None,
            "tensor_fp16_tflops": float(r.tensor_fp16_tflops) if r.tensor_fp16_tflops is not None else None,
            "performance_score": float(r.performance_score) if r.performance_score is not None else None,
            "health_score": float(r.health_score) if r.health_score is not None else None,
            "reputation_composite_score": float(r.reputation_composite_score) if r.reputation_composite_score is not None else None,
            "verification_level": r.verification_level,
            "price_per_hour_usd": float(r.price_per_hour_usd),
            "price_per_hour_inr": float(r.price_per_hour_inr),
            "region": r.region,
            "cpu_cores": r.cpu_cores,
            "ram_gb": float(r.ram_gb) if r.ram_gb is not None else None,
            "storage_gb": float(r.storage_gb) if r.storage_gb is not None else None,
            "os_type": r.os_type,
            "availability_status": r.availability_status,
            "created_at": r.created_at.isoformat(),
        }
        for r in scalars
    ]
