"""
Provisioning Service — Pydantic schemas.

Request/response models for all provisioning API endpoints.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from libs.db_models.provisioning_models import InstanceStatus
from libs.db_models.template_models import TemplateStatus


# ── Launch ─────────────────────────────────────────────────────────────────

class LaunchRequest(BaseModel):
    """Developer selects a listing and requests an instance."""
    listing_id: uuid.UUID = Field(..., description="The listing to rent")
    # Phase 6: optional one-click template launch
    template_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional template ID for a zero-setup AI workload launch. "
            "When provided, the scheduler validates hardware requirements and "
            "configures the container from the template's base_image and "
            "startup_command instead of a bare image."
        ),
    )


class InstanceResponse(BaseModel):
    """Returned on GET /instances/{id} and after launch."""
    id: uuid.UUID
    developer_id: uuid.UUID
    listing_id: uuid.UUID
    host_id: uuid.UUID
    # Phase 6: populated when instance was launched from a template
    template_id: uuid.UUID | None = None
    status: InstanceStatus
    hold_amount: Decimal
    hold_released: bool
    firecracker_vm_id: str | None
    wireguard_ip: str | None
    public_ip: str | None
    ssh_port: int
    billed_seconds: int
    price_per_second_usd: Decimal
    created_at: datetime
    started_at: datetime | None
    stopped_at: datetime | None
    terminated_at: datetime | None

    model_config = {"from_attributes": True}


class InstanceListResponse(BaseModel):
    items: list[InstanceResponse]
    total: int
    page: int
    page_size: int


# ── Connection info ────────────────────────────────────────────────────────

class ConnectionInfo(BaseModel):
    """Returned by GET /instances/{id}/connection."""
    instance_id: uuid.UUID
    status: InstanceStatus
    # SSH connection details
    ssh_host: str = Field(..., description="IP or relay host to SSH into")
    ssh_port: int
    ssh_user: str = Field(default="kynetic", description="Standard username inside the VM")
    # The decrypted private key PEM (only returned once per session, treat as secret)
    private_key_pem: str = Field(..., description="RSA private key PEM. Store securely; not re-issued.")
    public_key: str
    # Helper string ready to paste into terminal
    ssh_command: str = Field(..., description="e.g. 'ssh -i kynetic_key.pem kynetic@10.42.1.5 -p 22'")
    # When key auto-rotates
    key_expires_at: datetime | None


# ── Callbacks from host agent ──────────────────────────────────────────────

class ProvisioningCallback(BaseModel):
    """
    Posted by the host agent to /instances/callback when:
    - Provisioning completes (status=running)
    - Termination + deletion verified (status=terminated)
    """
    instance_id: uuid.UUID
    event: str = Field(..., description="'provisioning_complete' | 'deletion_verified' | 'failed'")
    firecracker_vm_id: str | None = None
    container_id: str | None = None
    # For deletion_verified events
    deletion_method: str | None = None
    deletion_hash: str | None = None
    deletion_payload: str | None = None
    # For failed events
    error_message: str | None = None
    extra: dict[str, Any] | None = None


# ── Stop / Terminate requests ──────────────────────────────────────────────

class StopRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class TerminateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    force: bool = Field(
        default=False,
        description="Skip graceful stop; immediately destroy the VM"
    )


# ── Secure deletion receipt ────────────────────────────────────────────────

class DeletionReceiptResponse(BaseModel):
    instance_id: uuid.UUID
    method: str
    agent_confirmation_hash: str
    verified_at: datetime

    model_config = {"from_attributes": True}


# ── Templates (Phase 6) ────────────────────────────────────────────────────

class TemplateResponse(BaseModel):
    """Returned by GET /templates and GET /templates/{id}."""
    id: uuid.UUID
    name: str
    slug: str
    description: str
    icon_emoji: str
    tags: list[str]
    base_image: str
    required_gpu_vram_gb: int | None
    required_ram_gb: int
    required_vcpus: int
    startup_command: str | None
    default_ssh_user: str
    exposed_web_ui_path: str | None
    web_ui_port: int | None
    status: TemplateStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    total: int


class CreateTemplateRequest(BaseModel):
    """Admin-only: register a new template image."""
    name: str = Field(..., max_length=120)
    slug: str = Field(..., max_length=80, pattern=r"^[a-z0-9-]+$")
    description: str = Field(..., max_length=2000)
    base_image: str = Field(..., max_length=512)
    icon_emoji: str = Field(default="🚀", max_length=8)
    tags: list[str] = Field(default_factory=list)
    required_gpu_vram_gb: int | None = None
    required_ram_gb: int = 8
    required_vcpus: int = 2
    startup_command: str | None = None
    exposed_web_ui_path: str | None = None
    web_ui_port: int | None = None


class WebUILinkResponse(BaseModel):
    """
    Returned by GET /instances/{id}/web-ui.

    The `web_ui_url` is a short-lived proxy URL for the browser UI exposed
    by the template (e.g. ComfyUI on port 8188, Stable Diffusion on 7860).
    It routes through the existing WireGuard relay — the raw host port is
    never directly exposed.
    """
    instance_id: uuid.UUID
    template_id: uuid.UUID
    web_ui_url: str = Field(
        ...,
        description="Proxy URL — include in browser. Valid until expires_at.",
    )
    token: str = Field(..., description="Bearer token embedded in web_ui_url")
    expires_at: datetime
    web_ui_port: int
    note: str = Field(
        default="This link expires in 1 hour. Request a new one after expiry."
    )
