"""Monitoring Service — Configuration."""

from functools import lru_cache

from libs.common.settings import BaseServiceSettings


class MonitoringSettings(BaseServiceSettings):
    service_name: str = "monitoring_service"
    port: int = 8011

    # JWT
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_A_LONG_RANDOM_SECRET"
    jwt_algorithm: str = "HS256"

    # Prometheus
    prometheus_multiproc_dir: str = "/tmp/prometheus_multiproc"

    # Internal service URLs for metrics aggregation
    provisioning_service_url: str = "http://provisioning_service:8004"
    wallet_billing_service_url: str = "http://wallet_billing_service:8003"
    host_service_url: str = "http://host_service:8002"


@lru_cache
def get_settings() -> MonitoringSettings:
    return MonitoringSettings()
