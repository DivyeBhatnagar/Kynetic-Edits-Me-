"""
Host Service — Pydantic request/response schemas.

The HostRegistrationRequest is the payload sent by the Host Agent
when it first contacts the backend. It includes the full hardware
manifest collected by hardware_detect.py.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from libs.db_models.host_models import (
    BenchmarkType,
    DiskType,
    HeartbeatStatus,
    HostStatus,
    OSType,
)


# ---------------------------------------------------------------------------
# Hardware spec sub-schema (sent by agent in registration + re-benchmark)
# ---------------------------------------------------------------------------
class HardwareSpecSchema(BaseModel):
    cpu_model: str | None = None
    cpu_cores: int = Field(ge=1)
    cpu_threads: int = Field(ge=1)
    ram_gb: float = Field(gt=0)
    disk_type: DiskType = DiskType.UNKNOWN
    disk_gb: float = Field(gt=0)
    gpu_model: str | None = None
    gpu_count: int = Field(ge=0, default=0)
    gpu_vram_gb: float | None = None
    driver_version: str | None = None
    cuda_version: str | None = None
    temperature_c: float | None = None
    power_draw_w: float | None = None
    raw_spec: dict | None = None


# ---------------------------------------------------------------------------
# Benchmark result sub-schema
# ---------------------------------------------------------------------------
class BenchmarkResultSchema(BaseModel):
    benchmark_type: BenchmarkType
    score: float = Field(gt=0)
    raw_metrics: dict | None = None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
class HostRegistrationRequest(BaseModel):
    """
    Sent by Host Agent on first contact.
    agent_id is a client-generated UUID persisted in the agent config
    (used to detect duplicate registrations and issue the right cert).
    """
    agent_id: uuid.UUID
    agent_version: str
    os_type: OSType
    hardware: HardwareSpecSchema


class HostRegistrationResponse(BaseModel):
    host_id: uuid.UUID
    status: HostStatus
    # PEM-encoded client certificate for mTLS; returned once at registration
    mtls_client_cert_pem: str
    message: str


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------
class HeartbeatRequest(BaseModel):
    host_id: uuid.UUID
    status: HeartbeatStatus
    temperature_c: float | None = None
    power_draw_w: float | None = None
    gpu_utilization_pct: float | None = None
    ram_used_gb: float | None = None


class HeartbeatResponse(BaseModel):
    received: bool = True
    host_status: HostStatus


# ---------------------------------------------------------------------------
# Benchmark submission
# ---------------------------------------------------------------------------
class BenchmarkSubmitRequest(BaseModel):
    host_id: uuid.UUID
    results: list[BenchmarkResultSchema]


class BenchmarkSubmitResponse(BaseModel):
    all_passed: bool
    host_status: HostStatus
    flags: list[str] = []


# ---------------------------------------------------------------------------
# Read schemas
# ---------------------------------------------------------------------------
class HardwareSpecResponse(BaseModel):
    cpu_model: str | None
    cpu_cores: int
    cpu_threads: int
    ram_gb: float
    disk_type: DiskType
    disk_gb: float
    gpu_model: str | None
    gpu_count: int
    gpu_vram_gb: float | None
    driver_version: str | None
    cuda_version: str | None
    reported_at: datetime

    model_config = {"from_attributes": True}


class BenchmarkResponse(BaseModel):
    id: uuid.UUID
    benchmark_type: BenchmarkType
    score: float
    raw_metrics: dict | None
    is_rerun: bool
    run_at: datetime

    model_config = {"from_attributes": True}


class HostResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    status: HostStatus
    os_type: OSType
    agent_version: str
    spec_verified: bool
    benchmark_verified: bool
    flagged_reason: str | None = None
    verification_level: str = "unverified"
    trust_state: str = "building_trust"
    hardware: HardwareSpecResponse | None = None
    latest_spec: HardwareSpecResponse | None = None
    created_at: datetime

    class Config:
        from_attributes = True


# ── Verification Schemas (v8 Feature 3) ───────────────────────────────────────

class VerificationDocumentSchema(BaseModel):
    document_type: str = Field("gov_id", description="gov_id, business_registration, bank_statement, utility_bill")
    storage_url: str = Field(..., description="Object storage S3/GCS URL")


class ApplyVerificationRequest(BaseModel):
    level: str = Field("silver", description="silver, gold, enterprise")
    documents: list[VerificationDocumentSchema] = []


class AdminReviewVerificationRequest(BaseModel):
    decision: str = Field("approved", description="approved or rejected")
    rejection_reason: str | None = None


class AdminRevokeVerificationRequest(BaseModel):
    reason: str = Field("Policy violation", description="Audit reason for revocation")
