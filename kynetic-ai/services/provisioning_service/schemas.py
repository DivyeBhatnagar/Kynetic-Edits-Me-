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


# ── Launch ─────────────────────────────────────────────────────────────────

class LaunchRequest(BaseModel):
    """Developer selects a listing and requests an instance."""
    listing_id: uuid.UUID = Field(..., description="The listing to rent")
    # Future: GPU count override, custom userdata script, etc.
    # Phase 7 will add AI-router-driven fields here.


class InstanceResponse(BaseModel):
    """Returned on GET /instances/{id} and after launch."""
    id: uuid.UUID
    developer_id: uuid.UUID
    listing_id: uuid.UUID
    host_id: uuid.UUID
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
