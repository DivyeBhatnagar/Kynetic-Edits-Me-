"""API Gateway settings."""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class APIGatewaySettings(BaseServiceSettings):
    service_name: str = "api_gateway"

    # JWT (must match auth_service values)
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # Internal service base URLs
    auth_service_url: str = "http://auth_service:8001"
    host_service_url: str = "http://host_service:8002"           # Phase 2
    marketplace_service_url: str = "http://marketplace_service:8003"  # Phase 3
    wallet_billing_service_url: str = "http://wallet_billing_service:8004"  # Phase 3
    provisioning_service_url: str = "http://provisioning_service:8005"
    ai_router_copilot_service_url: str = "http://ai_router_copilot_service:8006"
    reputation_pricing_service_url: str = "http://reputation_pricing_service:8007"
    hybrid_broker_service_url: str = "http://hybrid_broker_service:8008"
    monitoring_service_url: str = "http://monitoring_service:8009"


    # Rate limiting — per-IP, per-minute sliding window (Redis-backed)
    rate_limit_requests_per_minute: int = 60
    rate_limit_burst: int = 10  # Allow short bursts above the rate

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]


@lru_cache
def get_settings() -> APIGatewaySettings:
    return APIGatewaySettings()
