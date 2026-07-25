"""
Marketplace Service — async SQLAlchemy repository.
"""

import math
import uuid
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.marketplace_models import Listing, ListingStatus, ResourceType
from services.marketplace_service.schemas import (
    ListingCreate,
    ListingSearchParams,
    ListingUpdate,
)

logger = structlog.get_logger(__name__)


class ListingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Create ────────────────────────────────────────────────────────────────
    async def create(
        self,
        data: ListingCreate,
        owner_user_id: uuid.UUID,
        usd_to_inr_rate: Decimal,
        benchmark_scores: dict[str, Any] | None = None,
    ) -> Listing:
        """
        Create a listing.  Derives per-second prices and the missing currency
        price automatically from the FX rate.
        """
        # Resolve dual prices
        price_usd: Decimal
        price_inr: Decimal

        if data.price_per_hour_usd is not None:
            price_usd = data.price_per_hour_usd
            price_inr = (price_usd * usd_to_inr_rate).quantize(Decimal("0.000001"))
        else:
            price_inr = data.price_per_hour_inr  # type: ignore[assignment]
            price_usd = (price_inr / usd_to_inr_rate).quantize(Decimal("0.000001"))

        secs_per_hour = Decimal("3600")
        ps_usd = (price_usd / secs_per_hour).quantize(Decimal("0.0000000001"))
        ps_inr = (price_inr / secs_per_hour).quantize(Decimal("0.0000000001"))

        listing = Listing(
            host_id=data.host_id,
            owner_user_id=owner_user_id,
            resource_type=data.resource_type,
            gpu_model=data.gpu_model,
            gpu_count=data.gpu_count,
            gpu_vram_gb=data.gpu_vram_gb,
            cpu_cores=data.cpu_cores,
            ram_gb=data.ram_gb,
            storage_gb=data.storage_gb,
            storage_type=data.storage_type,
            price_per_hour_usd=price_usd,
            price_per_hour_inr=price_inr,
            price_per_second_usd=ps_usd,
            price_per_second_inr=ps_inr,
            region=data.region,
            benchmark_scores=benchmark_scores,
            status=ListingStatus.active,  # Auto-activate on creation
            title=data.title,
            description=data.description,
        )
        self._session.add(listing)
        await self._session.flush()
        await self._session.refresh(listing)
        logger.info(
            "listing_created",
            listing_id=str(listing.id),
            resource_type=listing.resource_type,
            price_usd=float(price_usd),
        )
        return listing

    # ── Read ──────────────────────────────────────────────────────────────────
    async def get_by_id(self, listing_id: uuid.UUID) -> Listing | None:
        result = await self._session.execute(
            select(Listing).where(Listing.id == listing_id)
        )
        return result.scalar_one_or_none()

    async def search(
        self, params: ListingSearchParams
    ) -> tuple[list[Listing], int]:
        """
        Browse listings with filters.  Returns (items, total_count) for pagination.
        """
        filters = []

        if params.available_only:
            filters.append(Listing.status == ListingStatus.active)
        elif params.resource_type is None:
            # If not filtering, at least exclude delisted
            filters.append(Listing.status != ListingStatus.delisted)

        if params.resource_type:
            filters.append(Listing.resource_type == params.resource_type)
        if params.gpu_model:
            filters.append(Listing.gpu_model.ilike(f"%{params.gpu_model}%"))
        if params.region:
            filters.append(Listing.region.ilike(f"%{params.region}%"))
        if params.min_price_usd is not None:
            filters.append(Listing.price_per_hour_usd >= params.min_price_usd)
        if params.max_price_usd is not None:
            filters.append(Listing.price_per_hour_usd <= params.max_price_usd)

        where_clause = and_(*filters) if filters else True

        # Count
        count_stmt = select(func.count()).select_from(Listing).where(where_clause)
        total = (await self._session.execute(count_stmt)).scalar_one()

        # Paginated rows
        offset = (params.page - 1) * params.page_size
        rows_stmt = (
            select(Listing)
            .where(where_clause)
            .order_by(Listing.created_at.desc())
            .offset(offset)
            .limit(params.page_size)
        )
        rows = (await self._session.execute(rows_stmt)).scalars().all()

        return list(rows), total

    # ── Update ────────────────────────────────────────────────────────────────
    async def update(
        self,
        listing: Listing,
        data: ListingUpdate,
        usd_to_inr_rate: Decimal,
    ) -> Listing:
        if data.status is not None:
            listing.status = data.status
        if data.title is not None:
            listing.title = data.title
        if data.description is not None:
            listing.description = data.description
        if data.region is not None:
            listing.region = data.region

        # Re-derive prices if either changes
        if data.price_per_hour_usd is not None or data.price_per_hour_inr is not None:
            if data.price_per_hour_usd is not None:
                price_usd = data.price_per_hour_usd
                price_inr = (price_usd * usd_to_inr_rate).quantize(Decimal("0.000001"))
            else:
                price_inr = data.price_per_hour_inr  # type: ignore[assignment]
                price_usd = (price_inr / usd_to_inr_rate).quantize(Decimal("0.000001"))

            secs = Decimal("3600")
            listing.price_per_hour_usd = price_usd
            listing.price_per_hour_inr = price_inr
            listing.price_per_second_usd = (price_usd / secs).quantize(Decimal("0.0000000001"))
            listing.price_per_second_inr = (price_inr / secs).quantize(Decimal("0.0000000001"))

        await self._session.flush()
        await self._session.refresh(listing)
        return listing

    # ── Delete (soft — delist) ────────────────────────────────────────────────
    async def delist(self, listing: Listing) -> Listing:
        listing.status = ListingStatus.delisted
        await self._session.flush()
        return listing

    # ── Availability sync helper ──────────────────────────────────────────────
    async def get_active_listing_ids(self) -> list[uuid.UUID]:
        """Return IDs of all active listings for Redis availability sync."""
        result = await self._session.execute(
            select(Listing.id).where(Listing.status == ListingStatus.active)
        )
        return list(result.scalars().all())
