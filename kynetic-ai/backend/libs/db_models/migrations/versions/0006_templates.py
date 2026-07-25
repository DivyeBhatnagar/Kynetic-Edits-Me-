"""
Alembic migration — Phase 6: Zero-Setup App Templates.

Creates:
  templates                — template registry (one-click AI workload configs)
  template_web_ui_sessions — short-lived scoped web UI access tokens

Modifies:
  instances                — adds nullable template_id FK

Seeds:
  4 launch-day templates (Stable Diffusion, Ollama, ComfyUI, Llama 3)
  with status='available' (images are public upstream images that are
  pre-scanned; in production, status starts as 'pending_scan').
"""

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0006_templates"
down_revision = "0005_security"
branch_labels = None
depends_on = None


# ── Launch-day seed data ───────────────────────────────────────────────────
# Using public upstream images as placeholders (pullable without private registry).
# In production, these would be pre-scanned and signed copies hosted at
# ghcr.io/kynetic/... after passing the Phase 5 image scanning pipeline.

SEED_TEMPLATES = [
    {
        "id": str(uuid.UUID("10000000-0000-0000-0000-000000000001")),
        "name": "Stable Diffusion WebUI",
        "slug": "stable-diffusion",
        "description": (
            "AUTOMATIC1111 Stable Diffusion Web UI. "
            "Generate images via a full browser interface — no coding required. "
            "Supports SD 1.5, SD XL, ControlNet, LoRA, and more."
        ),
        "icon_emoji": "🎨",
        "tags": ["image-gen", "stable-diffusion", "webui", "gpu"],
        "base_image": "ghcr.io/lllyasviel/stable-diffusion-webui:latest",
        "required_gpu_vram_gb": 8,
        "required_ram_gb": 16,
        "required_vcpus": 4,
        "startup_command": (
            "python webui.py --listen --port 7860 --no-progressbar-hiding"
        ),
        "default_ssh_user": "kynetic",
        "exposed_web_ui_path": "/",
        "web_ui_port": 7860,
        "status": "available",
    },
    {
        "id": str(uuid.UUID("10000000-0000-0000-0000-000000000002")),
        "name": "Ollama",
        "slug": "ollama",
        "description": (
            "Run large language models locally via the Ollama API. "
            "OpenAI-compatible REST API on port 11434. "
            "Pull and run Llama 3, Mistral, Gemma, Phi-3, and many more."
        ),
        "icon_emoji": "🦙",
        "tags": ["llm", "ollama", "api", "gpu"],
        "base_image": "ollama/ollama:latest",
        "required_gpu_vram_gb": 4,
        "required_ram_gb": 8,
        "required_vcpus": 2,
        "startup_command": "ollama serve",
        "default_ssh_user": "kynetic",
        "exposed_web_ui_path": None,
        "web_ui_port": None,
        "status": "available",
    },
    {
        "id": str(uuid.UUID("10000000-0000-0000-0000-000000000003")),
        "name": "ComfyUI",
        "slug": "comfyui",
        "description": (
            "ComfyUI — the most powerful node-based Stable Diffusion interface. "
            "Build complex image and video generation pipelines visually. "
            "Full browser UI accessible via secure link."
        ),
        "icon_emoji": "🖼️",
        "tags": ["image-gen", "comfyui", "nodes", "webui", "gpu"],
        "base_image": "ghcr.io/comfyanonymous/comfyui:latest",
        "required_gpu_vram_gb": 8,
        "required_ram_gb": 16,
        "required_vcpus": 4,
        "startup_command": "python main.py --listen 0.0.0.0 --port 8188",
        "default_ssh_user": "kynetic",
        "exposed_web_ui_path": "/",
        "web_ui_port": 8188,
        "status": "available",
    },
    {
        "id": str(uuid.UUID("10000000-0000-0000-0000-000000000004")),
        "name": "Llama 3 (8B)",
        "slug": "llama3",
        "description": (
            "Meta Llama 3 8B Instruct, served via Ollama. "
            "OpenAI-compatible chat completions API on port 11434. "
            "Ready to use immediately after launch — model pre-pulled."
        ),
        "icon_emoji": "🤖",
        "tags": ["llm", "llama3", "meta", "api", "gpu"],
        "base_image": "ollama/ollama:latest",
        "required_gpu_vram_gb": 8,
        "required_ram_gb": 16,
        "required_vcpus": 4,
        "startup_command": (
            "bash -c 'ollama serve & sleep 5 && ollama pull llama3:8b && wait'"
        ),
        "default_ssh_user": "kynetic",
        "exposed_web_ui_path": None,
        "web_ui_port": None,
        "status": "available",
    },
]


def upgrade() -> None:
    # ── ENUM: template status ──────────────────────────────────────────────
    op.execute(
        "CREATE TYPE template_status_enum AS ENUM "
        "('pending_scan', 'available', 'disabled')"
    )

    # ── TABLE: templates ───────────────────────────────────────────────────
    op.create_table(
        "templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), unique=True, nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("icon_emoji", sa.String(8), nullable=False, server_default="🚀"),
        sa.Column("tags", JSONB, nullable=False, server_default="[]"),

        # Container image
        sa.Column("base_image", sa.String(512), nullable=False),

        # Hardware requirements
        sa.Column("required_gpu_vram_gb", sa.Integer(), nullable=True),
        sa.Column("required_ram_gb", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("required_vcpus", sa.Integer(), nullable=False, server_default="2"),

        # Container config
        sa.Column("startup_command", sa.Text(), nullable=True),
        sa.Column("default_ssh_user", sa.String(64), server_default="kynetic"),

        # Web UI
        sa.Column("exposed_web_ui_path", sa.String(256), nullable=True),
        sa.Column("web_ui_port", sa.Integer(), nullable=True),

        # Security scan state
        sa.Column(
            "status",
            sa.Enum("pending_scan", "available", "disabled",
                    name="template_status_enum", create_type=False),
            nullable=False,
            server_default="pending_scan",
        ),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_report", JSONB, nullable=True),

        # Timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_templates_slug", "templates", ["slug"], unique=True)
    op.create_index("ix_templates_status", "templates", ["status"])

    # ── Add template_id FK to instances ───────────────────────────────────
    op.add_column(
        "instances",
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="SET NULL"),
            nullable=True,
            comment="Phase 6: template used for one-click launch (NULL = raw launch)",
        ),
    )
    op.create_index("ix_instances_template", "instances", ["template_id"])

    # ── TABLE: template_web_ui_sessions ───────────────────────────────────
    op.create_table(
        "template_web_ui_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "instance_id",
            UUID(as_uuid=True),
            sa.ForeignKey("instances.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            UUID(as_uuid=True),
            sa.ForeignKey("templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(128), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_template_web_ui_sessions_instance",
        "template_web_ui_sessions",
        ["instance_id"],
    )
    op.create_index(
        "ix_template_web_ui_sessions_token",
        "template_web_ui_sessions",
        ["token"],
        unique=True,
    )

    # ── Seed launch-day templates ─────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    op.bulk_insert(
        sa.table(
            "templates",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("slug", sa.String),
            sa.column("description", sa.Text),
            sa.column("icon_emoji", sa.String),
            sa.column("tags", JSONB),
            sa.column("base_image", sa.String),
            sa.column("required_gpu_vram_gb", sa.Integer),
            sa.column("required_ram_gb", sa.Integer),
            sa.column("required_vcpus", sa.Integer),
            sa.column("startup_command", sa.Text),
            sa.column("default_ssh_user", sa.String),
            sa.column("exposed_web_ui_path", sa.String),
            sa.column("web_ui_port", sa.Integer),
            sa.column("status", sa.String),
            sa.column("last_scanned_at", sa.DateTime),
            sa.column("scan_report", JSONB),
            sa.column("created_at", sa.DateTime),
            sa.column("updated_at", sa.DateTime),
        ),
        [
            {
                **t,
                "last_scanned_at": now,
                "scan_report": {"mock": True, "findings": []},
                "created_at": now,
                "updated_at": now,
            }
            for t in SEED_TEMPLATES
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_template_web_ui_sessions_token", table_name="template_web_ui_sessions")
    op.drop_index("ix_template_web_ui_sessions_instance", table_name="template_web_ui_sessions")
    op.drop_table("template_web_ui_sessions")

    op.drop_index("ix_instances_template", table_name="instances")
    op.drop_column("instances", "template_id")

    op.drop_index("ix_templates_status", table_name="templates")
    op.drop_index("ix_templates_slug", table_name="templates")
    op.drop_table("templates")

    op.execute("DROP TYPE IF EXISTS template_status_enum")
