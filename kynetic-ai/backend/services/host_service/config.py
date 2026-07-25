"""Host Service settings."""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class HostServiceSettings(BaseServiceSettings):
    service_name: str = "host_service"

    # mTLS — CA cert and key used to sign agent client certificates at registration
    mtls_ca_cert_path: str = "certs/ca.crt"
    mtls_ca_key_path: str = "certs/ca.key"
    agent_cert_validity_days: int = 365

    # Heartbeat
    heartbeat_timeout_seconds: int = 120    # Host marked offline after this silence

    # Benchmark thresholds for automatic flagging
    # If a GPU reports VRAM > this ratio above the known spec, flag it
    vram_mismatch_tolerance_pct: float = 10.0

    # Re-benchmark schedule (hours between forced re-runs per active host)
    rebenchmark_interval_hours: int = 48

    # JWT (shared with auth_service — for verifying host-owner Bearer tokens)
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]


@lru_cache
def get_settings() -> HostServiceSettings:
    return HostServiceSettings()
