"""
Provisioning Service — Pydantic schemas.

Request/response models for all provisioning API endpoints.
Phase 30: Formalized schemas for InstanceCreateRequest, InstanceActionResponse,
InstanceConnectionResponse, and explicit action responses.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid

from pydantic import BaseModel, Field, field_validator

from libs.db_models.provisioning_models import InstanceStatus
from libs.db_models.template_models import TemplateStatus


# ── Launch & Instance Create ───────────────────────────────────────────────

class InstanceCreateRequest(BaseModel):
    """
    Phase 30: Formalized instance creation request with requested_hours field validation.
    """
    listing_id: uuid.UUID = Field(..., description="The listing to rent")
    developer_id: uuid.UUID | None = Field(
        default=None,
        description="Optional explicit developer ID (defaults to authenticated user)",
    )
    template_id: uuid.UUID | None = Field(
        default=None,
        description=(
            "Optional template ID for a zero-setup AI workload launch. "
            "When provided, configures the container from template specifications."
        ),
    )
    requested_hours: Decimal = Field(
        default=Decimal("1.0"),
        gt=Decimal("0"),
        le=Decimal("720.0"),  # max 30 days
        description="Duration hold requested in hours (max 720 hours / 30 days)",
    )

    @field_validator("requested_hours")
    @classmethod
    def round_to_hour_precision(cls, v: Decimal) -> Decimal:
        from decimal import ROUND_HALF_UP
        return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# Backward-compatible alias for existing launch endpoint
LaunchRequest = InstanceCreateRequest


class InstanceResponse(BaseModel):
    """Returned on GET /instances/{id} and after launch."""
    id: uuid.UUID
    developer_id: uuid.UUID
    listing_id: uuid.UUID
    host_id: uuid.UUID
    template_id: uuid.UUID | None = None
    status: InstanceStatus
    hold_amount: Decimal
    hold_released: bool
    firecracker_vm_id: str | None = None
    wireguard_ip: str | None = None
    public_ip: str | None = None
    ssh_port: int = 22
    billed_seconds: int = 0
    price_per_second_usd: Decimal
    created_at: datetime
    started_at: datetime | None = None
    stopped_at: datetime | None = None
    terminated_at: datetime | None = None

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
    ssh_host: str = Field(..., description="IP or relay host to SSH into")
    ssh_port: int
    ssh_user: str = Field(default="kynetic", description="Standard username inside the VM")
    private_key_pem: str = Field(..., description="RSA private key PEM. Store securely; not re-issued.")
    public_key: str
    ssh_command: str = Field(..., description="e.g. 'ssh -i kynetic_key.pem kynetic@10.42.1.5 -p 22'")
    key_expires_at: datetime | None = None


class InstanceConnectionResponse(BaseModel):
    """Phase 30: Structured connection response summary."""
    instance_id: uuid.UUID
    ssh_command: str | None = None
    web_ui_url: str | None = None
    expires_at: datetime


# ── Actions & Callbacks ───────────────────────────────────────────────────

class InstanceActionResponse(BaseModel):
    """Phase 30: Explicit response model for instance actions (start, stop, terminate)."""
    instance_id: uuid.UUID
    status: InstanceStatus
    message: str


class ProvisioningCallback(BaseModel):
    """Posted by the host agent to /instances/callback."""
    instance_id: uuid.UUID
    event: str = Field(..., description="'provisioning_complete' | 'deletion_verified' | 'failed'")
    firecracker_vm_id: str | None = None
    container_id: str | None = None
    deletion_method: str | None = None
    deletion_hash: str | None = None
    deletion_payload: str | None = None
    error_message: str | None = None
    extra: dict[str, Any] | None = None


class StopRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class TerminateRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    force: bool = Field(
        default=False,
        description="Skip graceful stop; immediately destroy the VM"
    )


class DeletionReceiptResponse(BaseModel):
    instance_id: uuid.UUID
    method: str
    agent_confirmation_hash: str
    verified_at: datetime

    model_config = {"from_attributes": True}


# ── Templates ─────────────────────────────────────────────────────────────

class TemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str
    icon_emoji: str
    tags: list[str]
    base_image: str
    required_gpu_vram_gb: int | None = None
    required_ram_gb: int
    required_vcpus: int
    startup_command: str | None = None
    default_ssh_user: str
    exposed_web_ui_path: str | None = None
    web_ui_port: int | None = None
    status: TemplateStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class TemplateListResponse(BaseModel):
    items: list[TemplateResponse]
    total: int


class CreateTemplateRequest(BaseModel):
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
