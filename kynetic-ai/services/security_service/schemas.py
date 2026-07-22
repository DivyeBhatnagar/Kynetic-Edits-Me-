"""
Security Service — Pydantic schemas.
"""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from libs.db_models.security_models import (
    KillSwitchTargetType,
    SecurityEventSeverity,
    SecurityEventType,
    TrustTierLevel,
)


# ── Kill Switch ────────────────────────────────────────────────────────────

class KillSwitchRequest(BaseModel):
    target_type: KillSwitchTargetType
    target_id: str = Field(..., description="UUID of the instance, host, or user account")
    reason: str | None = Field(default=None, max_length=1000)


class KillSwitchResponse(BaseModel):
    id: uuid.UUID
    target_type: KillSwitchTargetType
    target_id: str
    triggered_by: uuid.UUID | None
    reason: str | None
    triggered_at: datetime
    broadcast_result: dict[str, Any] | None

    model_config = {"from_attributes": True}


# ── Security Events ────────────────────────────────────────────────────────

class SecurityEventResponse(BaseModel):
    id: uuid.UUID
    event_type: SecurityEventType
    severity: SecurityEventSeverity
    resource_type: str | None
    resource_id: str | None
    user_id: uuid.UUID | None
    ip_address: str | None
    details: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class SecurityEventListResponse(BaseModel):
    items: list[SecurityEventResponse]
    total: int
    page: int
    page_size: int


# ── Trust Tier ─────────────────────────────────────────────────────────────

class TrustTierResponse(BaseModel):
    user_id: uuid.UUID
    tier: TrustTierLevel
    max_instance_vcpus: int | None
    max_gpu_vram_gb: int | None
    max_gpu_hours_month: int | None
    max_spend_usd_month: float | None
    is_wallet_frozen: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class TrustTierUpdateRequest(BaseModel):
    """Admin-only: manually set a user's trust tier."""
    tier: TrustTierLevel
    max_instance_vcpus: int | None = None
    max_gpu_vram_gb: int | None = None
    max_gpu_hours_month: int | None = None
    max_spend_usd_month: float | None = None
    is_wallet_frozen: bool = False
    reason: str | None = Field(default=None, max_length=500)


# ── Image scan ────────────────────────────────────────────────────────────

class ImageScanResult(BaseModel):
    image: str
    passed: bool
    finding_count: int
    critical_count: int
    high_count: int
    blocked: bool
    details: list[dict[str, Any]] = Field(default_factory=list)
    mock: bool = False


# ── Device Fingerprint ─────────────────────────────────────────────────────

class FingerprintRequest(BaseModel):
    """Posted from the frontend at login/signup to record the device fingerprint."""
    fingerprint_hash: str = Field(..., min_length=64, max_length=64,
                                  description="SHA-256 hex string of client-side signals")
    ip_address: str | None = None
    user_agent: str | None = None


class FingerprintCheckResponse(BaseModel):
    fingerprint_hash: str
    is_new_device: bool
    multi_account_suspected: bool
    matching_user_count: int


# ── Identity Verification ──────────────────────────────────────────────────

class IDVerificationRequest(BaseModel):
    """Phase 5 stub — full OCR + liveness check is Phase 10."""
    document_type: str = Field(..., description="passport | national_id | drivers_license")
    # In production: pre-signed upload URL returned separately;
    # here we just record the claim and set tier pending manual review
    claim_document_uploaded: bool = True


class IDVerificationResponse(BaseModel):
    user_id: uuid.UUID
    status: str  # "pending_review" | "approved" | "rejected"
    message: str


# ── Fraud detection ────────────────────────────────────────────────────────

class FraudScanResult(BaseModel):
    user_id: uuid.UUID
    flagged: bool
    rules_triggered: list[str]
    details: dict[str, Any] = Field(default_factory=dict)
