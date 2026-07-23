"""Marketplace Service settings."""

from decimal import Decimal
from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class MarketplaceSettings(BaseServiceSettings):
    service_name: str = "marketplace_service"

    # JWT (shared with gateway)
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # Host Service URL (to verify host status at listing creation)
    host_service_url: str = "http://host_service:8002"

    # Reputation & Pricing Service URL (Phase 8)
    reputation_pricing_service_url: str = "http://reputation_pricing_service:8008"

    # FX — fixed rate for Phase 3 (live FX wired in Phase 8)
    usd_to_inr_rate: Decimal = Decimal("84.0")

    # Redis availability index
    listings_available_key: str = "kynetic:listings:available"
    listings_cache_ttl_seconds: int = 300  # 5 min TTL for per-listing cache

    # Availability sync
    availability_sync_interval_minutes: int = 5


@lru_cache
def get_settings() -> MarketplaceSettings:
    return MarketplaceSettings()
