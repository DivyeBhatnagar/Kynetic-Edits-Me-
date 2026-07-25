"""
Marketplace Service — Pydantic schemas.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from libs.db_models.marketplace_models import ListingStatus, ResourceType


# ── Listing Create ─────────────────────────────────────────────────────────

class ListingCreate(BaseModel):
    """Request body for POST /listings."""

    host_id: uuid.UUID
    resource_type: ResourceType

    # Hardware — only the relevant subset need be filled
    gpu_model: str | None = None
    gpu_count: int | None = None
    gpu_vram_gb: float | None = None
    cpu_cores: int | None = None
    ram_gb: float | None = None
    storage_gb: float | None = None
    storage_type: str | None = None  # "nvme" | "ssd" | "hdd"

    # Pricing — provide ONE of: price_per_hour_usd or price_per_hour_inr.
    # The other is computed automatically from the FX rate.
    price_per_hour_usd: Decimal | None = Field(None, ge=0)
    price_per_hour_inr: Decimal | None = Field(None, ge=0)

    region: str | None = None
    title: str | None = Field(None, max_length=200)
    description: str | None = None

    @model_validator(mode="after")
    def require_at_least_one_price(self) -> "ListingCreate":
        if self.price_per_hour_usd is None and self.price_per_hour_inr is None:
            raise ValueError("Provide at least one of price_per_hour_usd or price_per_hour_inr")
        return self


class ListingUpdate(BaseModel):
    """Request body for PATCH /listings/{id}."""

    price_per_hour_usd: Decimal | None = Field(None, ge=0)
    price_per_hour_inr: Decimal | None = Field(None, ge=0)
    status: ListingStatus | None = None
    title: str | None = Field(None, max_length=200)
    description: str | None = None
    region: str | None = None


# ── Listing Response ───────────────────────────────────────────────────────

class ListingResponse(BaseModel):
    """Full listing detail response."""

    id: uuid.UUID
    host_id: uuid.UUID
    owner_user_id: uuid.UUID
    resource_type: ResourceType
    gpu_model: str | None
    gpu_count: int | None
    gpu_vram_gb: float | None
    cpu_cores: int | None
    ram_gb: float | None
    storage_gb: float | None
    storage_type: str | None
    price_per_hour_usd: Decimal
    price_per_hour_inr: Decimal
    price_per_second_usd: Decimal
    price_per_second_inr: Decimal
    region: str | None
    benchmark_scores: dict[str, Any] | None
    status: ListingStatus
    title: str | None
    description: str | None
    is_available: bool = False  # Injected from Redis availability index
    # Phase 8: reputation score injected from reputation_pricing_service
    reputation_score: float | None = None
    reputation_components: dict[str, float | None] | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ListingBrief(BaseModel):
    """Compact listing card for browse/search results."""

    id: uuid.UUID
    resource_type: ResourceType
    gpu_model: str | None
    cpu_cores: int | None
    ram_gb: float | None
    price_per_hour_usd: Decimal
    price_per_hour_inr: Decimal
    region: str | None
    status: ListingStatus
    is_available: bool = False
    title: str | None
    # Phase 8: reputation score injected from reputation_pricing_service
    reputation_score: float | None = None

    class Config:
        from_attributes = True


# ── Search / Filter ────────────────────────────────────────────────────────

class ListingFilters(BaseModel):
    """Query parameters for GET /search/listings."""

    resource_type: ResourceType | None = None
    gpu_model: str | None = None
    min_vram_gb: float | None = None
    max_price_usd: Decimal | None = None
    region: str | None = None
    min_reputation: float | None = None
    sort: str = "price_asc"
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)


# ── Smart Search & GPU Benchmark DB Schemas (v8 Features 4 & 5) ─────────────

class SearchableListingResponse(BaseModel):
    listing_id: uuid.UUID
    host_id: uuid.UUID
    gpu_model: str | None = None
    vram_gb: float | None = None
    tensor_fp16_tflops: float | None = None
    performance_score: float | None = None
    health_score: float | None = None
    reputation_composite_score: float | None = None
    verification_level: str = "unverified"
    price_per_hour_usd: float
    price_per_hour_inr: float
    region: str = "us-east"
    cpu_cores: int | None = None
    ram_gb: float | None = None
    storage_gb: float | None = None
    os_type: str | None = None
    availability_status: str = "active"
    created_at: str


class GpuModelSummaryResponse(BaseModel):
    gpu_model: str
    region: str = "global"
    avg_tensor_fp16_tflops: float | None = None
    avg_tensor_fp32_tflops: float | None = None
    avg_mem_bandwidth_gbps: float | None = None
    sample_count: int = 0
    last_refreshed: str


class GpuModelCompareResponse(BaseModel):
    model_a: str
    model_b: str
    stats_a: GpuModelSummaryResponse | None = None
    stats_b: GpuModelSummaryResponse | None = None
    speedup_ratio_fp16: float | None = None
    recommendation: str


class PricePerformanceResponse(BaseModel):
    gpu_model: str
    region: str = "global"
    avg_price_per_hour_usd: float
    avg_performance_score: float
    price_performance_ratio: float
    last_refreshed: str


class ListingSearchParams(BaseModel):
    """Query parameters for GET /listings."""

    resource_type: ResourceType | None = None
    gpu_model: str | None = None
    min_price_usd: Decimal | None = Field(None, ge=0)
    max_price_usd: Decimal | None = Field(None, ge=0)
    region: str | None = None
    available_only: bool = True  # Only show active + available listings by default
    # Phase 8 — reputation score filter (now LIVE, was placeholder in Phase 3)
    min_reputation_score: float | None = Field(None, ge=0.0, le=1.0)
    sort_by_reputation: bool = False  # Sort by composite_score DESC when True

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)

    @model_validator(mode="after")
    def validate_price_range(self) -> "ListingSearchParams":
        if (
            self.min_price_usd is not None
            and self.max_price_usd is not None
            and self.min_price_usd > self.max_price_usd
        ):
            raise ValueError("min_price_usd must be <= max_price_usd")
        return self


class ListingSearchResponse(BaseModel):
    """Paginated listing browse response."""

    items: list[ListingBrief]
    total: int
    page: int
    page_size: int
    total_pages: int
