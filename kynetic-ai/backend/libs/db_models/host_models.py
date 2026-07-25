"""
Phase 2 database models: hosts, host_hardware_specs, host_benchmarks, host_heartbeats.

State machine for host lifecycle:
  pending_verification → benchmarking → verified → listed
                                      → flagged (spec mismatch)
                                      → suspended

Design notes:
- host_heartbeats uses table partitioning by month (via partition_by hint in comments)
  to handle high-volume time-series data without degrading query performance.
- benchmark scores are stored as floats alongside raw JSONB for full fidelity.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from libs.db_models.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class HostStatus(str, enum.Enum):
    PENDING_VERIFICATION = "pending_verification"
    BENCHMARKING = "benchmarking"
    VERIFIED = "verified"
    LISTED = "listed"          # Phase 3 sets this when listing is created
    FLAGGED = "flagged"        # Spec mismatch detected
    SUSPENDED = "suspended"    # Admin action or abuse


class OSType(str, enum.Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"


class BenchmarkType(str, enum.Enum):
    LLM_INFERENCE = "llm_inference"   # tokens/sec on fixed small model
    IMAGE_GEN = "image_gen"           # time-to-complete fixed SD step count
    FLOPS = "flops"                   # raw matrix-multiply throughput


class HeartbeatStatus(str, enum.Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class DiskType(str, enum.Enum):
    NVME = "nvme"
    SSD = "ssd"
    HDD = "hdd"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------
class Region(Base):
    __tablename__ = "regions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    country_code: Mapped[str] = mapped_column(String(10), nullable=False)
    latency_pop_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Hosts
# ---------------------------------------------------------------------------
class Host(Base):
    """
    Central host record — created by POST /hosts/register.
    Drives the host lifecycle state machine.
    """
    __tablename__ = "hosts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("regions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[HostStatus] = mapped_column(
        Enum(HostStatus, name="host_status"),
        nullable=False,
        default=HostStatus.PENDING_VERIFICATION,
        index=True,
    )
    os_type: Mapped[OSType] = mapped_column(
        Enum(OSType, name="os_type"), nullable=False
    )
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    # SHA-256 fingerprint of the agent's mTLS client certificate
    mtls_cert_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True,
        comment="SHA-256 fingerprint of client cert issued at registration"
    )
    # Verification flags
    spec_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    benchmark_verified: Mapped[bool] = mapped_column(default=False, nullable=False)
    flagged_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    hardware_specs: Mapped[list["HostHardwareSpec"]] = relationship(
        "HostHardwareSpec", back_populates="host", order_by="HostHardwareSpec.reported_at.desc()"
    )
    benchmarks: Mapped[list["HostBenchmark"]] = relationship(
        "HostBenchmark", back_populates="host"
    )
    heartbeats: Mapped[list["HostHeartbeat"]] = relationship(
        "HostHeartbeat", back_populates="host"
    )
    machines: Mapped[list["Machine"]] = relationship(
        "Machine", back_populates="host", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Host id={self.id} status={self.status} os={self.os_type}>"


# ---------------------------------------------------------------------------
# Section 5 Physical Hardware Models: Machine, GPU, CPUSpec, RAMSpec, StorageSpec
# ---------------------------------------------------------------------------
class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hosts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    public_ip_hint: Mapped[str | None] = mapped_column(String(45), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    host: Mapped["Host"] = relationship("Host", back_populates="machines")
    gpus: Mapped[list["GPU"]] = relationship("GPU", back_populates="machine", cascade="all, delete-orphan")
    cpu_spec: Mapped["CPUSpec | None"] = relationship("CPUSpec", back_populates="machine", uselist=False, cascade="all, delete-orphan")
    ram_spec: Mapped["RAMSpec | None"] = relationship("RAMSpec", back_populates="machine", uselist=False, cascade="all, delete-orphan")
    storage_specs: Mapped[list["StorageSpec"]] = relationship("StorageSpec", back_populates="machine", cascade="all, delete-orphan")


class GPU(Base):
    __tablename__ = "gpus"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    vram_gb: Mapped[float] = mapped_column(Float, nullable=False)
    driver_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cuda_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    benchmark_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cc_capable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cc_mode_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    machine: Mapped["Machine"] = relationship("Machine", back_populates="gpus")


class CPUSpec(Base):
    __tablename__ = "cpu_specs"

    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), primary_key=True
    )
    cores: Mapped[int] = mapped_column(Integer, nullable=False)
    threads: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clock_ghz: Mapped[float | None] = mapped_column(Float, nullable=True)

    machine: Mapped["Machine"] = relationship("Machine", back_populates="cpu_spec")


class RAMSpec(Base):
    __tablename__ = "ram_specs"

    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), primary_key=True
    )
    total_gb: Mapped[float] = mapped_column(Float, nullable=False)
    ram_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    speed_mhz: Mapped[int | None] = mapped_column(Integer, nullable=True)

    machine: Mapped["Machine"] = relationship("Machine", back_populates="ram_spec")


class StorageSpec(Base):
    __tablename__ = "storage_specs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    machine_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("machines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    disk_type: Mapped[DiskType] = mapped_column(
        Enum(DiskType, name="disk_type"), nullable=False, default=DiskType.UNKNOWN
    )
    capacity_gb: Mapped[float] = mapped_column(Float, nullable=False)

    machine: Mapped["Machine"] = relationship("Machine", back_populates="storage_specs")



# ---------------------------------------------------------------------------
# Host Hardware Specs
# ---------------------------------------------------------------------------
class HostHardwareSpec(Base):
    """
    Hardware specification snapshot reported by the Host Agent.
    Multiple snapshots per host (one per registration + re-benchmark).
    The latest entry is the authoritative spec.
    """
    __tablename__ = "host_hardware_specs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # CPU
    cpu_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cpu_cores: Mapped[int] = mapped_column(Integer, nullable=False)
    cpu_threads: Mapped[int] = mapped_column(Integer, nullable=False)
    # RAM
    ram_gb: Mapped[float] = mapped_column(Float, nullable=False)
    # Disk
    disk_type: Mapped[DiskType] = mapped_column(
        Enum(DiskType, name="disk_type"), nullable=False, default=DiskType.UNKNOWN
    )
    disk_gb: Mapped[float] = mapped_column(Float, nullable=False)
    # GPU (nullable — CPU-only hosts have no GPU)
    gpu_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gpu_vram_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    driver_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cuda_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Telemetry at time of report
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_draw_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Raw full spec payload for forward compatibility
    raw_spec: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    reported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    host: Mapped["Host"] = relationship("Host", back_populates="hardware_specs")

    __table_args__ = (
        Index("ix_host_hardware_specs_host_reported", "host_id", "reported_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<HostHardwareSpec host={self.host_id} "
            f"gpu={self.gpu_model} vram={self.gpu_vram_gb}GB>"
        )


# ---------------------------------------------------------------------------
# Host Benchmarks
# ---------------------------------------------------------------------------
class HostBenchmark(Base):
    """
    Benchmark run result. One row per (host, benchmark_type, run).
    Used by Auto-Pricing (Phase 8) and AI Router (Phase 7).
    """
    __tablename__ = "host_benchmarks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    benchmark_type: Mapped[BenchmarkType] = mapped_column(
        Enum(BenchmarkType, name="benchmark_type"), nullable=False
    )
    # Primary score (normalised, comparable across machines)
    # LLM_INFERENCE: tokens/sec | IMAGE_GEN: steps/sec | FLOPS: TFLOPS
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # Full benchmark output for analysis
    raw_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Whether this run was triggered by periodic re-benchmark or initial onboarding
    is_rerun: Mapped[bool] = mapped_column(default=False, nullable=False)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    host: Mapped["Host"] = relationship("Host", back_populates="benchmarks")

    __table_args__ = (
        Index("ix_host_benchmarks_host_type", "host_id", "benchmark_type"),
        Index("ix_host_benchmarks_type_score", "benchmark_type", "score"),
    )

    def __repr__(self) -> str:
        return (
            f"<HostBenchmark host={self.host_id} type={self.benchmark_type} score={self.score}>"
        )


# ---------------------------------------------------------------------------
# Host Heartbeats
# ---------------------------------------------------------------------------
class HostHeartbeat(Base):
    """
    Periodic status + telemetry ping from the Host Agent.
    High-volume time-series table — partition by month in production.

    NOTE: In production, consider moving to TimescaleDB hypertables or
    PostgreSQL range partitioning (PARTITION BY RANGE (recorded_at)) for
    efficient queries on recent data without scanning full table.
    """
    __tablename__ = "host_heartbeats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[HeartbeatStatus] = mapped_column(
        Enum(HeartbeatStatus, name="heartbeat_status"), nullable=False
    )
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_draw_w: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    ram_used_gb: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    host: Mapped["Host"] = relationship("Host", back_populates="heartbeats")

    __table_args__ = (
        Index("ix_host_heartbeats_host_recorded", "host_id", "recorded_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<HostHeartbeat host={self.host_id} status={self.status} at={self.recorded_at}>"
        )


# ---------------------------------------------------------------------------
# Phase 29 — Host Commands
# ---------------------------------------------------------------------------
class CommandType(str, enum.Enum):
    LAUNCH = "launch"
    STOP = "stop"
    TERMINATE = "terminate"


class CommandStatus(str, enum.Enum):
    SENT = "sent"
    ACKED = "acked"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


class HostCommand(Base):
    """
    Phase 29 — Audit trail of commands sent to Host Agents.
    Records every signed, idempotent command issued to a host.
    """
    __tablename__ = "host_commands"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    host_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hosts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    command_type: Mapped[CommandType] = mapped_column(
        Enum(CommandType, name="command_type_enum", create_type=True),
        nullable=False,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True
    )
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus, name="command_status_enum", create_type=True),
        nullable=False,
        default=CommandStatus.SENT,
        index=True,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    acked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_host_commands_host_instance", "host_id", "instance_id"),
    )

