"""
Phase 13 — Observability, Alerting & Incident Response ORM Models

Two tables:
  alert_events    — history audit log of all fired Prometheus/Alertmanager alerts
  incident_records — operational incident tracking log with root cause & resolution
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
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

class AlertSeverity(str, enum.Enum):
    critical = "critical"
    warning  = "warning"
    info     = "info"


class AlertStatus(str, enum.Enum):
    firing     = "firing"
    resolved   = "resolved"
    suppressed = "suppressed"


class IncidentSeverity(str, enum.Enum):
    sev1 = "SEV1"
    sev2 = "SEV2"
    sev3 = "SEV3"
    sev4 = "SEV4"


class IncidentStatus(str, enum.Enum):
    investigating = "investigating"
    identified    = "identified"
    monitoring    = "monitoring"
    resolved      = "resolved"


# ---------------------------------------------------------------------------
# AlertEvent — history log of triggered Prometheus/Alertmanager alerts
# ---------------------------------------------------------------------------

class AlertEvent(Base):
    """
    Audit log recording every alert fired by Alertmanager.
    Used for alert analytics, noisy alert tuning, and post-mortem timelines.
    """
    __tablename__ = "alert_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    alert_name: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity, name="alert_severity"),
        nullable=False
    )
    service_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status"),
        nullable=False,
        default=AlertStatus.firing
    )
    labels: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("idx_alert_events_name_status",
              "alert_name", "status", "fired_at"),
        Index("idx_alert_events_severity", "severity"),
    )


# ---------------------------------------------------------------------------
# IncidentRecord — operational incident log
# ---------------------------------------------------------------------------

class IncidentRecord(Base):
    """
    Tracked operational incident records with timeline, root cause analysis,
    and resolution steps.
    """
    __tablename__ = "incident_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    severity: Mapped[IncidentSeverity] = mapped_column(
        Enum(IncidentSeverity, name="incident_severity"),
        nullable=False
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status"),
        nullable=False,
        default=IncidentStatus.investigating
    )
    lead_responder: Mapped[str | None] = mapped_column(String(200), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    impact_ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_incident_records_status_sev",
              "status", "severity", "created_at"),
    )
