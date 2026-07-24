"""
Phase 31 Unit Tests — Audit Logging & Host Agent Diagnostics.

Tests:
  - log_instance_event DB table row creation & structlog emission
  - log_validation_rejection recording of Phase 27 gate failures
  - JobDiagnostics timing metrics collector & error stack trace formatting
"""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from host_agent.diagnostics import JobDiagnostics
from libs.db_models.database import Base
from libs.db_models.user_models import AuditLog, User, UserRole
from services.provisioning_service.audit import log_instance_event, log_validation_rejection

# ── DB fixture ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_AUDIT_TABLES = [
    User.__table__,
    AuditLog.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        for table in reversed(_AUDIT_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in _AUDIT_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_AUDIT_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    yield
    async with _engine.begin() as conn:
        for table in reversed(_AUDIT_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


# ── Audit Logger Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_instance_event_creates_audit_log_row(db: AsyncSession):
    actor_id = uuid.uuid4()
    instance_id = uuid.uuid4()

    async with db.begin():
        await log_instance_event(
            db,
            actor_id=actor_id,
            instance_id=instance_id,
            action="create",
            metadata={"listing_id": "list-123"},
        )

    result = await db.execute(select(AuditLog).where(AuditLog.action == "create"))
    row = result.scalar_one_or_none()

    assert row is not None
    assert row.actor_id == actor_id
    assert row.resource_id == str(instance_id)
    assert row.resource_type == "instance"
    assert row.extra_data == {"listing_id": "list-123"}


@pytest.mark.asyncio
async def test_log_validation_rejection_creates_audit_log_row(db: AsyncSession):
    actor_id = uuid.uuid4()
    listing_id = uuid.uuid4()

    async with db.begin():
        await log_validation_rejection(
            db,
            requester_id=actor_id,
            listing_id=listing_id,
            code="INSUFFICIENT_BALANCE",
            message="Required $10.00, available $0.00",
        )

    result = await db.execute(
        select(AuditLog).where(AuditLog.action == "validation_rejected")
    )
    row = result.scalar_one_or_none()

    assert row is not None
    assert row.actor_id == actor_id
    assert row.extra_data["code"] == "INSUFFICIENT_BALANCE"
    assert "Required $10.00" in row.extra_data["message"]


# ── Host Diagnostics Collector Tests ─────────────────────────────────────

def test_job_diagnostics_success_metrics():
    diag = JobDiagnostics(instance_id="inst-999", host_id="host-1")
    diag.record_stage("pulling_image")
    diag.record_image_pull(1.25)
    diag.record_volume_setup(0.45)
    diag.record_firecracker_boot(0.12)

    report = diag.mark_success()

    assert report["instance_id"] == "inst-999"
    assert report["success"] is True
    assert report["stage"] == "completed"
    assert report["timing_ms"]["image_pull"] == 1250.0
    assert report["timing_ms"]["volume_setup"] == 450.0
    assert report["timing_ms"]["firecracker_boot"] == 120.0
    assert report["timing_ms"]["total"] >= 0.0


def test_job_diagnostics_failure_capture():
    diag = JobDiagnostics(instance_id="inst-fail-123")
    diag.record_stage("allocating_nvme")

    try:
        raise RuntimeError("Disk quota exceeded on NVMe volume")
    except Exception as exc:
        report = diag.mark_failed(exc)

    assert report["success"] is False
    assert report["stage"] == "allocating_nvme"
    assert report["error"]["message"] == "Disk quota exceeded on NVMe volume"
    assert "RuntimeError" in report["error"]["trace"]
