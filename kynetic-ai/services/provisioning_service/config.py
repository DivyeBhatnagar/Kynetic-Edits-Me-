"""
Provisioning Service — Configuration.

All values are read from environment variables (12-factor).
Sensitive defaults are dev-only placeholders that MUST be overridden
in production via secrets management.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ProvisioningSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── Application ────────────────────────────────────────────────────────
    app_name: str = "provisioning_service"
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 8005

    # ── Database ───────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic"

    # ── Redis / Celery ─────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── Service URLs (internal) ────────────────────────────────────────────
    wallet_billing_service_url: str = "http://wallet_billing_service:8004"
    marketplace_service_url: str = "http://marketplace_service:8003"
    host_service_url: str = "http://host_service:8002"
    security_service_url: str = "http://security_service:8006"   # Phase 5

    # ── mTLS ───────────────────────────────────────────────────────────────
    # Paths to certs used when calling host agents over mTLS
    mtls_ca_cert_path: str = "/certs/ca.crt"
    mtls_client_cert_path: str = "/certs/provisioning.crt"
    mtls_client_key_path: str = "/certs/provisioning.key"

    # ── SSH Key Security ───────────────────────────────────────────────────
    # Fernet key for encrypting SSH private keys in DB.
    # Generate with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ssh_key_fernet_key: str = "REPLACE_WITH_32_BYTE_BASE64_URL_FERNET_KEY_IN_PRODUCTION="
    ssh_key_size_bits: int = 4096
    # How long (seconds) before an SSH session key is auto-rotated
    ssh_key_rotation_seconds: int = 3600  # 1 hour

    # ── WireGuard Relay ────────────────────────────────────────────────────
    wireguard_relay_host: str = "relay.kynetic.ai"
    wireguard_relay_public_key: str = "REPLACE_WITH_RELAY_WG_PUBLIC_KEY"
    wireguard_subnet: str = "10.42.0.0/16"
    # Port range for WireGuard peer allocation
    wireguard_port_start: int = 51820
    wireguard_port_end: int = 59900

    # ── Billing ────────────────────────────────────────────────────────────
    # How many seconds of compute cost to hold upfront on launch
    hold_hours: float = 1.0
    # When balance drops below this many seconds of remaining runtime → emit warning
    low_balance_warning_seconds: int = 300  # 5 minutes of remaining runtime

    # ── Firecracker ────────────────────────────────────────────────────────
    # Set FIRECRACKER_MOCK=true on macOS / CI (no KVM available)
    firecracker_mock: bool = False
    firecracker_socket_path: str = "/tmp/firecracker.sock"

    # ── Auth (shared JWT secret with auth_service) ─────────────────────────
    jwt_secret_key: str = "dev_secret_change_in_production_12345"
    jwt_algorithm: str = "HS256"


@lru_cache
def get_settings() -> ProvisioningSettings:
    return ProvisioningSettings()
