"""
Phase 12 — Infrastructure, Deployment & Environments ORM Models

Three tables:
  deployment_releases   — immutable audit log of every deploy event
  environment_configs   — non-secret per-environment config audit trail
  service_health_checks — automated health check results for trending
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from libs.db_models.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DeployStatus(str, enum.Enum):
    started     = "started"
    success     = "success"
    failed      = "failed"
    rolled_back = "rolled_back"


class HealthStatus(str, enum.Enum):
    healthy   = "healthy"
    degraded  = "degraded"
    unhealthy = "unhealthy"


class DeployEnvironment(str, enum.Enum):
    dev        = "dev"
    staging    = "staging"
    production = "production"


# ---------------------------------------------------------------------------
# DeploymentRelease — immutable audit log of every deployment event
# ---------------------------------------------------------------------------

class DeploymentRelease(Base):
    """
    Append-only record of every deployment event across all services and environments.

    Populated by the GitHub Actions deploy.yml workflow on each run.
    Never updated — a rollback creates a new record rather than modifying an existing one.
    """
    __tablename__ = "deployment_releases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    image_tag: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="Short git SHA (e.g. abc12345) — matches ECR image tag"
    )
    environment: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="dev | staging | production"
    )
    git_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    git_ref: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="Branch or tag ref (e.g. refs/heads/main)"
    )
    deployed_by: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
        comment="GitHub actor or username who triggered the deploy"
    )
    status: Mapped[DeployStatus] = mapped_column(
        Enum(DeployStatus, name="deploy_status"),
        nullable=False,
        default=DeployStatus.started
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    migration_revision: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Alembic revision applied with this deploy"
    )

    __table_args__ = (
        Index("idx_deployment_releases_env_service",
              "environment", "service_name", "started_at"),
        Index("idx_deployment_releases_status", "status"),
    )


# ---------------------------------------------------------------------------
# EnvironmentConfig — non-secret per-environment configuration audit trail
# ---------------------------------------------------------------------------

class EnvironmentConfig(Base):
    """
    Stores non-secret configuration values per environment with a full audit trail.

    IMPORTANT: This table MUST NOT store secrets (API keys, passwords, tokens).
    It is for non-sensitive runtime config values only (e.g. USD_TO_INR_RATE,
    RATE_LIMIT_REQUESTS_PER_MINUTE, ENVIRONMENT name).

    Secrets live exclusively in AWS Secrets Manager / Vault.
    """
    __tablename__ = "environment_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    set_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="Set when this key-value pair is replaced by a newer entry — never deleted"
    )

    __table_args__ = (
        Index("idx_environment_configs_lookup",
              "environment", "key", "superseded_at"),
    )


# ---------------------------------------------------------------------------
# ServiceHealthCheck — automated health check result log
# ---------------------------------------------------------------------------

class ServiceHealthCheck(Base):
    """
    Time-series record of automated /health probe results per service per environment.

    Written by the monitoring_service on each polling cycle.
    Used for trending health history and SLA calculations.
    """
    __tablename__ = "service_health_checks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_name: Mapped[str] = mapped_column(String(100), nullable=False)
    environment: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[HealthStatus] = mapped_column(
        Enum(HealthStatus, name="health_status"),
        nullable=False
    )
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_service_health_recent",
              "service_name", "environment", "checked_at"),
    )
