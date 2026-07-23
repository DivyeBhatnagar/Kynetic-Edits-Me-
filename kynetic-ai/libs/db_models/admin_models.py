"""
Phase 15 — Admin Panel & Internal Operations ORM Models

Three tables:
  admin_users          — SSO internal admin user accounts and RBAC roles
  ticket_activity_logs — support ticket resolution history log
  fraud_review_queue   — flagged user/host trust and security review items
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from libs.db_models.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AdminRole(str, enum.Enum):
    support    = "support"
    finance    = "finance"
    security   = "security"
    superadmin = "superadmin"


class TicketAction(str, enum.Enum):
    assigned  = "assigned"
    responded = "responded"
    resolved  = "resolved"
    escalated = "escalated"


class FraudStatus(str, enum.Enum):
    pending   = "pending"
    approved  = "approved"
    rejected  = "rejected"
    suspended = "suspended"


# ---------------------------------------------------------------------------
# AdminUser — internal SSO team account
# ---------------------------------------------------------------------------

class AdminUser(Base):
    """
    Internal operator account used for authentication into the admin panel.
    Role permissions enforced by RBAC middleware.
    """
    __tablename__ = "admin_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    role: Mapped[AdminRole] = mapped_column(
        Enum(AdminRole, name="admin_role"),
        nullable=False
    )
    sso_subject: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_admin_users_email", "email"),
        Index("idx_admin_users_role", "role"),
    )


# ---------------------------------------------------------------------------
# TicketActivityLog — support resolution history
# ---------------------------------------------------------------------------

class TicketActivityLog(Base):
    """
    Activity audit log tracking support ticket assignments, responses, and state transitions.
    """
    __tablename__ = "ticket_activity_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    admin_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[TicketAction] = mapped_column(
        Enum(TicketAction, name="ticket_action"),
        nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_ticket_activity_ticket", "ticket_id", "created_at"),
    )


# ---------------------------------------------------------------------------
# FraudReviewItem — fraud review queue
# ---------------------------------------------------------------------------

class FraudReviewItem(Base):
    """
    Queue item surfacing flagged accounts (from device fingerprints, security logs, or low reputation).
    """
    __tablename__ = "fraud_review_queue"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    host_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    status: Mapped[FraudStatus] = mapped_column(
        Enum(FraudStatus, name="fraud_status"),
        nullable=False,
        default=FraudStatus.pending
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("idx_fraud_queue_status_risk", "status", "risk_score", "created_at"),
    )
