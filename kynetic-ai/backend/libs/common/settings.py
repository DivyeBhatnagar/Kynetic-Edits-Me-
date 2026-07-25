"""
Shared Pydantic settings base for all Kynetic AI services.

Each service creates its own Settings class inheriting from BaseServiceSettings,
adding service-specific fields. All settings load from environment variables
(and optionally from a .env file in local dev).

Usage in a service:
    from libs.common.settings import BaseServiceSettings

    class AuthServiceSettings(BaseServiceSettings):
        jwt_secret: str
        jwt_algorithm: str = "HS256"
        access_token_expire_minutes: int = 15

    settings = AuthServiceSettings()
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BaseServiceSettings(BaseSettings):
    """
    Common settings shared across all Kynetic AI backend services.
    Override by inheriting and adding service-specific fields.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown env vars — each service declares its own
    )

    # ── Service Identity ───────────────────────────────────────────────────────
    service_name: str = Field(default="kynetic-service", description="Human-readable service name")
    environment: str = Field(default="development", description="development | staging | production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # ── Database ───────────────────────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic",
        description="Async PostgreSQL connection URL",
    )

    # ── Redis ──────────────────────────────────────────────────────────────────
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL (used for cache, sessions, and Celery broker)",
    )

    # ── Celery ─────────────────────────────────────────────────────────────────
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery result backend URL",
    )

    # ── API Gateway ────────────────────────────────────────────────────────────
    api_gateway_url: str = Field(
        default="http://api_gateway:8000",
        description="Internal API Gateway base URL for inter-service calls",
    )

    @property
    def is_production(self) -> bool:
        return self.environment == "production"
