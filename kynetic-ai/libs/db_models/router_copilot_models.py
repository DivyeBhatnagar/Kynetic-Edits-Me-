"""
Phase 7 DB Models: AI Resource Router & AI Copilot.

Tables:
  router_recommendations — audit trail + future ML training data for router calls
  copilot_sessions       — one session per developer conversation thread
  copilot_messages       — individual turns (user | assistant) within a session
"""

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.db_models.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class RouterGoal(str, enum.Enum):
    fastest = "fastest"
    cheapest = "cheapest"
    balanced = "balanced"


# ── Models ────────────────────────────────────────────────────────────────────

class RouterRecommendation(Base):
    """
    Immutable audit record of every /router/recommend call.

    Stores the raw request payload and the ranked listing IDs that were
    returned.  Used for:
      - Developer auditability ("why was this recommended?")
      - Future ML training data (Phase 8+ can join with job outcome data)
      - Rate-limit abuse investigation

    NOTE: Never update rows — only INSERT.  If the recommendation changes
    (e.g. re-rank on stale data), create a new row.
    """

    __tablename__ = "router_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    developer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Full request payload (budget + currency OR goal + template_id)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # Ordered list of listing IDs returned, most-recommended first
    recommended_listing_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    # Full ranked results with scores for transparency
    ranked_results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("ix_router_recs_developer_created", "developer_id", "created_at"),
    )


class CopilotSession(Base):
    """
    A stateful conversation session between a developer and the AI Copilot.

    Scoped to a single developer.  Sessions are created on the first
    POST /copilot/chat call and remain open until explicitly closed or
    TTL-expired (application-level cleanup, not DB-level).
    """

    __tablename__ = "copilot_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    developer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Optional label set by the frontend for UX purposes
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    messages: Mapped[list["CopilotMessage"]] = relationship(
        "CopilotMessage",
        back_populates="session",
        order_by="CopilotMessage.created_at.asc()",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_copilot_sessions_developer", "developer_id"),
    )


class CopilotMessage(Base):
    """
    A single turn in a CopilotSession.

    role = 'user'      → free-text from the developer
    role = 'assistant' → structured narration from the LangChain copilot agent

    The assistant message always includes a `router_recommendation_id` reference
    so the numbers it quotes are fully traceable to a RouterRecommendation row
    (satisfying the "no hallucinated numbers" requirement).
    """

    __tablename__ = "copilot_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[MessageRole] = mapped_column(
        Enum(MessageRole, name="message_role_enum", create_type=True),
        nullable=False,
    )

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # FK to the RouterRecommendation that grounded this assistant reply
    # (NULL for user messages and assistant messages that don't trigger the router)
    router_recommendation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("router_recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    session: Mapped["CopilotSession"] = relationship(back_populates="messages")

    __table_args__ = (
        Index("ix_copilot_messages_session_created", "session_id", "created_at"),
    )
