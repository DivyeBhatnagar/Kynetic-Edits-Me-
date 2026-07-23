"""
Template Models — Phase 6: Zero-Setup App Templates.

Defines the Template registry and TemplateWebUISession tables.
Templates are pre-built, scanned, verified container images mapped
to a launch configuration, enabling one-click AI workload launches.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.db_models.database import Base


# ── Enums ──────────────────────────────────────────────────────────────────

class TemplateStatus(str, enum.Enum):
    pending_scan = "pending_scan"   # Queued for image scanning (Phase 5 pipeline)
    available    = "available"      # Scanned, signed, ready for one-click launch
    disabled     = "disabled"       # Scan failed / admin-disabled


# ── Tables ─────────────────────────────────────────────────────────────────

class Template(Base):
    """
    A pre-built, scanned container image mapped to an AI workload launch config.

    Templates are config-driven: adding a new template requires only a DB row,
    not a code change to the provisioning path.

    All four launch-day templates are seeded in migration 0006_templates.py:
      - stable-diffusion  (AUTOMATIC1111 WebUI, port 7860, 8 GB VRAM)
      - ollama            (Ollama API server, port 11434, 4 GB VRAM)
      - comfyui           (ComfyUI node editor, port 8188, 8 GB VRAM)
      - llama3            (Llama 3 8B via Ollama, port 11434, 8 GB VRAM)
    """

    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Human-readable identifiers
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon_emoji: Mapped[str] = mapped_column(String(8), nullable=False, default="🚀")
    tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=list)

    # Container image — every template image goes through Phase 5 scanning
    # before being marked `available`.
    base_image: Mapped[str] = mapped_column(String(512), nullable=False)

    # Minimum hardware requirements — enforced by scheduler before launch
    required_gpu_vram_gb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required_ram_gb: Mapped[int]             = mapped_column(Integer, nullable=False, default=8)
    required_vcpus: Mapped[int]              = mapped_column(Integer, nullable=False, default=2)

    # Container configuration
    startup_command: Mapped[str | None]      = mapped_column(Text, nullable=True)
    default_ssh_user: Mapped[str]            = mapped_column(String(64), default="kynetic")

    # Web UI (ComfyUI, Stable Diffusion expose a browser UI)
    # If NULL → SSH/API access only.
    exposed_web_ui_path: Mapped[str | None]  = mapped_column(String(256), nullable=True)
    web_ui_port: Mapped[int | None]          = mapped_column(Integer, nullable=True)

    # Security scan status (Phase 5 pipeline integration)
    status: Mapped[TemplateStatus] = mapped_column(
        Enum(TemplateStatus, name="template_status_enum"),
        nullable=False,
        default=TemplateStatus.pending_scan,
        index=True,
    )
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scan_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Back-reference to instances launched from this template
    instances: Mapped[list] = relationship(
        "Instance",
        back_populates="template",
        lazy="noload",
    )

    # Web UI sessions issued for instances of this template
    web_ui_sessions: Mapped[list] = relationship(
        "TemplateWebUISession",
        back_populates="template",
        lazy="noload",
    )


class TemplateWebUISession(Base):
    """
    Short-lived, scoped web UI access token for templates that expose a browser UI.

    When a developer requests the web UI link for a running instance launched
    from a template with `web_ui_port` set, we issue one of these tokens:
      - Token is a random UUID (treated as a secret bearer token)
      - Routed through the existing WireGuard relay infrastructure — never a
        raw public port exposure
      - Revoked automatically when the instance terminates

    The gateway (or a thin proxy sidecar) validates the token and forwards
    traffic to `wireguard_ip:web_ui_port` on the host.
    """

    __tablename__ = "template_web_ui_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("templates.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The opaque token the developer includes in their web UI request
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)

    # When this session expires (UTC)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Revoked on instance termination or explicit call
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    template: Mapped["Template"] = relationship(
        "Template", back_populates="web_ui_sessions", lazy="noload"
    )
