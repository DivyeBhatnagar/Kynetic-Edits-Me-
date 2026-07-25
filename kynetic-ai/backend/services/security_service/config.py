"""
Security Service — Settings.

Port: 8006
"""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class SecurityServiceSettings(BaseServiceSettings):
    service_name: str = "security_service"

    # Internal service URLs
    provisioning_service_url: str = "http://provisioning_service:8005"
    wallet_billing_service_url: str = "http://wallet_billing_service:8004"
    host_service_url: str = "http://host_service:8002"

    # JWT (must match auth_service)
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # Admin JWT secret (separate key for admin-only endpoints)
    admin_jwt_secret_key: str = "CHANGE_ME_ADMIN_SECRET"

    # Celery
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Redis (rate limiting)
    redis_url: str = "redis://redis:6379/0"

    # Image scanning
    # In mock mode (SCANNER_MOCK=true) all images pass with zero findings
    scanner_mock: bool = True
    trivy_binary: str = "/usr/local/bin/trivy"
    # Block execution if any finding has severity >= this level
    scan_block_severity: str = "HIGH"  # Options: UNKNOWN, LOW, MEDIUM, HIGH, CRITICAL

    # Rate limiting defaults (per IP per minute)
    rate_limit_default_rpm: int = 60
    rate_limit_burst: int = 10
    rate_limit_auth_rpm: int = 20        # stricter on auth routes
    rate_limit_admin_rpm: int = 30

    # Crypto-mining detection
    # Hash-rate threshold above which we suspect mining (tokens/s for LLM workloads are normally <5)
    mining_suspected_hashrate_threshold: float = 1_000_000.0
    # Keywords in process names that indicate mining
    mining_process_keywords: list[str] = ["xmrig", "cgminer", "bfgminer", "ethminer", "nbminer"]

    # Fraud detection
    # Flag if > this many top-ups happen in < this many minutes
    fraud_topup_count_threshold: int = 3
    fraud_topup_window_minutes: int = 10

    # Trust tier default caps (unverified accounts)
    trust_default_max_vcpus: int = 2
    trust_default_max_gpu_hours: int = 10
    trust_default_max_spend_usd: float = 50.0


@lru_cache
def get_settings() -> SecurityServiceSettings:
    return SecurityServiceSettings()
