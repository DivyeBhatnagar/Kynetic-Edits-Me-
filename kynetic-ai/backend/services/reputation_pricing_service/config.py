"""reputation_pricing_service settings."""

from decimal import Decimal
from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class ReputationPricingSettings(BaseServiceSettings):
    service_name: str = "reputation_pricing_service"

    # JWT (shared with gateway)
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # ── Reputation score weights (must sum to 1.0) ─────────────────────────
    # Transparent, explainable — per Phase 8 spec preference for trust-critical scoring.
    weight_uptime: float = 0.30
    weight_latency: float = 0.15
    weight_network: float = 0.10
    weight_job_success: float = 0.25
    weight_benchmark: float = 0.10
    weight_response_time: float = 0.10

    # Heartbeat window for uptime computation (days)
    uptime_window_days: int = 30
    # Expected heartbeats per day (Phase 2 sends every 60s → 1440/day)
    expected_heartbeats_per_day: int = 1440

    # ── Auto-pricing model settings ────────────────────────────────────────
    pricing_model_version: str = "v1"
    # Fallback floor/cap to protect against model outliers
    pricing_floor_usd: Decimal = Decimal("0.05")
    pricing_cap_usd: Decimal = Decimal("50.00")

    # ── Electricity cost (configurable per region, default US average) ─────
    electricity_kwh_rate_usd: Decimal = Decimal("0.12")  # $/kWh

    # ── FX ─────────────────────────────────────────────────────────────────
    usd_to_inr_rate: Decimal = Decimal("84.0")

    # ── Internal service URLs ──────────────────────────────────────────────
    host_service_url: str = "http://host_service:8002"
    marketplace_service_url: str = "http://marketplace_service:8003"


@lru_cache
def get_settings() -> ReputationPricingSettings:
    return ReputationPricingSettings()
