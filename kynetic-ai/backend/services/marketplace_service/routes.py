"""
Marketplace Service — API routes.

Endpoints:
  POST   /listings              create a listing (verified host required)
  GET    /listings              browse/search/filter
  GET    /listings/{id}         full listing detail
  PATCH  /listings/{id}         update price/status (owner only)
  DELETE /listings/{id}         delist (owner only)
"""

import math
import uuid

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from services.marketplace_service import availability as avail
from services.marketplace_service.config import get_settings
from services.marketplace_service.repository import ListingRepository
from services.marketplace_service.schemas import (
    ListingBrief,
    ListingCreate,
    ListingResponse,
    ListingSearchParams,
    ListingSearchResponse,
    ListingUpdate,
)
from libs.common.auth import require_auth

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/listings", tags=["Listings"])
settings = get_settings()


# ── Helpers ────────────────────────────────────────────────────────────────

async def _assert_host_verified(host_id: uuid.UUID, owner_user_id: uuid.UUID) -> dict:
    """
    Call host_service to verify:
      1. The host exists
      2. host.status == 'verified'
      3. The requesting user owns the host

    Returns the host dict on success; raises 403/404 on failure.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.host_service_url}/hosts/{host_id}",
            )
        except Exception as exc:
            logger.error("host_service_unreachable", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Host service unavailable. Try again later.",
            )

    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Host not found.")

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify host status.",
        )

    host = resp.json()
    if str(host.get("owner_user_id")) != str(owner_user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this host.",
        )
    if host.get("status") != "verified":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Host is not verified (current status: {host.get('status')}). "
                   "Complete hardware verification before listing.",
        )
    return host


# ── Routes ─────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=ListingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a listing from a verified host",
)
async def create_listing(
    body: ListingCreate,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    owner_id = uuid.UUID(auth["sub"])
    host = await _assert_host_verified(body.host_id, owner_id)

    # Snapshot benchmark scores from host record
    benchmark_scores = host.get("latest_benchmarks")

    repo = ListingRepository(session)
    listing = await repo.create(
        data=body,
        owner_user_id=owner_id,
        usd_to_inr_rate=settings.usd_to_inr_rate,
        benchmark_scores=benchmark_scores,
    )
    await session.commit()

    # Add to Redis availability index immediately
    await avail.mark_available(settings.redis_url, listing.id)

    # ── Phase 8: fire-and-ignore pricing suggestion ────────────────────────
    # Non-blocking: if reputation_pricing_service is down, listing creation succeeds.
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.get(
                f"{settings.reputation_pricing_service_url}/v1/pricing/suggest",
                params={"listing_id": str(listing.id)},
                headers={"Authorization": f"Bearer {auth.get('_raw_token', '')}"},
            )
    except Exception:
        pass  # Pricing suggestion is best-effort; never blocks listing creation

    result = ListingResponse.model_validate(listing)
    result.is_available = True
    return result


@router.get(
    "",
    response_model=ListingSearchResponse,
    summary="Browse / search / filter compute listings",
)
async def search_listings(
    resource_type: str | None = Query(None),
    gpu_model: str | None = Query(None),
    min_price_usd: float | None = Query(None, ge=0),
    max_price_usd: float | None = Query(None, ge=0),
    region: str | None = Query(None),
    available_only: bool = Query(True),
    min_reputation_score: float | None = Query(None, ge=0.0, le=1.0, description="Phase 8: filter by minimum composite reputation score"),
    sort_by_reputation: bool = Query(False, description="Phase 8: sort results by reputation score descending"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db_session),
):
    from decimal import Decimal
    from libs.db_models.marketplace_models import ResourceType

    params = ListingSearchParams(
        resource_type=ResourceType(resource_type) if resource_type else None,
        gpu_model=gpu_model,
        min_price_usd=Decimal(str(min_price_usd)) if min_price_usd is not None else None,
        max_price_usd=Decimal(str(max_price_usd)) if max_price_usd is not None else None,
        region=region,
        available_only=available_only,
        min_reputation_score=min_reputation_score,
        sort_by_reputation=sort_by_reputation,
        page=page,
        page_size=page_size,
    )

    repo = ListingRepository(session)
    listings, total = await repo.search(params)

    # Enrich is_available from Redis
    available_ids = await avail.get_available_ids(settings.redis_url)

    # ── Phase 8: Fetch reputation scores for all returned listings ────────
    host_ids = list({str(l.host_id) for l in listings})
    reputation_by_host: dict[str, float] = {}
    if host_ids:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                # Batch fetch: query each host's latest score from reputation service
                import asyncio as _asyncio
                async def _fetch_rep(hid: str) -> tuple[str, float]:
                    try:
                        r = await client.get(
                            f"{settings.reputation_pricing_service_url}/v1/hosts/{hid}/reputation"
                        )
                        if r.status_code == 200:
                            return hid, r.json().get("composite_score", 0.5)
                    except Exception:
                        pass
                    return hid, 0.5  # Neutral fallback
                results = await _asyncio.gather(*[_fetch_rep(hid) for hid in host_ids])
                reputation_by_host = dict(results)
        except Exception:
            pass  # Reputation enrichment is best-effort

    items = []
    for l in listings:
        # ── Reputation filter (Phase 8 — now live) ─────────────────────────
        rep_score = reputation_by_host.get(str(l.host_id), 0.5)
        if params.min_reputation_score is not None and rep_score < params.min_reputation_score:
            continue  # Filter out below-threshold hosts

        brief = ListingBrief.model_validate(l)
        brief.is_available = str(l.id) in available_ids
        brief.reputation_score = rep_score
        items.append(brief)

    # ── Sort by reputation if requested ───────────────────────────────────
    if params.sort_by_reputation:
        items.sort(key=lambda x: x.reputation_score or 0.0, reverse=True)

    total_pages = math.ceil(total / page_size) if total > 0 else 1
    return ListingSearchResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get(
    "/{listing_id}",
    response_model=ListingResponse,
    summary="Get full listing detail",
)
async def get_listing(
    listing_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
):
    repo = ListingRepository(session)
    listing = await repo.get_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")

    result = ListingResponse.model_validate(listing)
    result.is_available = await avail.is_available(settings.redis_url, listing_id)

    # ── Phase 8: enrich with reputation score + components ─────────────────
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            rep_resp = await client.get(
                f"{settings.reputation_pricing_service_url}/v1/hosts/{listing.host_id}/reputation"
            )
            if rep_resp.status_code == 200:
                rep_data = rep_resp.json()
                result.reputation_score = rep_data.get("composite_score")
                result.reputation_components = rep_data.get("components")
    except Exception:
        pass  # Non-critical

    return result


@router.patch(
    "/{listing_id}",
    response_model=ListingResponse,
    summary="Update listing price or status (owner only)",
)
async def update_listing(
    listing_id: uuid.UUID,
    body: ListingUpdate,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    owner_id = uuid.UUID(auth["sub"])
    repo = ListingRepository(session)
    listing = await repo.get_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    if listing.owner_user_id != owner_id:
        raise HTTPException(status_code=403, detail="You do not own this listing.")

    listing = await repo.update(listing, body, settings.usd_to_inr_rate)
    await session.commit()

    # Sync availability on status change
    from libs.db_models.marketplace_models import ListingStatus
    if listing.status == ListingStatus.active:
        await avail.mark_available(settings.redis_url, listing.id)
    else:
        await avail.mark_unavailable(settings.redis_url, listing.id)

    result = ListingResponse.model_validate(listing)
    result.is_available = listing.status == ListingStatus.active
    return result


@router.delete(
    "/{listing_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delist a listing (owner only)",
)
async def delist_listing(
    listing_id: uuid.UUID,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    owner_id = uuid.UUID(auth["sub"])
    repo = ListingRepository(session)
    listing = await repo.get_by_id(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found.")
    if listing.owner_user_id != owner_id:
        raise HTTPException(status_code=403, detail="You do not own this listing.")

    await repo.delist(listing)
    await session.commit()
    await avail.mark_unavailable(settings.redis_url, listing.id)
