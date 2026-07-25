"""
Alembic migration — Phase 7: AI Resource Router & AI Copilot.

Creates:
  router_recommendations — immutable audit log of every /router/recommend call
  copilot_sessions       — one session per developer conversation thread
  copilot_messages       — individual turns (user | assistant) within a session
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0007_router_copilot"
down_revision = "0006_templates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Enums ────────────────────────────────────────────────────────────────
    message_role_enum = sa.Enum("user", "assistant", name="message_role_enum")
    message_role_enum.create(op.get_bind(), checkfirst=True)

    # ── router_recommendations ────────────────────────────────────────────────
    op.create_table(
        "router_recommendations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "developer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("request_payload", JSONB, nullable=False),
        sa.Column("recommended_listing_ids", JSONB, nullable=False),
        sa.Column("ranked_results", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_router_recs_developer_created",
        "router_recommendations",
        ["developer_id", "created_at"],
    )

    # ── copilot_sessions ──────────────────────────────────────────────────────
    op.create_table(
        "copilot_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "developer_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_copilot_sessions_developer",
        "copilot_sessions",
        ["developer_id"],
    )

    # ── copilot_messages ──────────────────────────────────────────────────────
    op.create_table(
        "copilot_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("copilot_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", message_role_enum, nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column(
            "router_recommendation_id",
            UUID(as_uuid=True),
            sa.ForeignKey("router_recommendations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_copilot_messages_session_created",
        "copilot_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("copilot_messages")
    op.drop_table("copilot_sessions")
    op.drop_table("router_recommendations")
    sa.Enum(name="message_role_enum").drop(op.get_bind(), checkfirst=True)
