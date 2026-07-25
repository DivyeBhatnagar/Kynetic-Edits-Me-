"""
Phase 29 Unit Tests — Host Agent Command Channel & Idempotency.

Tests:
  - send_launch_command audit row creation & ack status
  - send_stop_command audit row creation & ack status
  - send_terminate_command audit row creation & ack status
  - Idempotency store deduplication (replay prevention)
  - Command error and timeout tracking in DB audit table
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from host_agent.command_listener import HostAgentCommandServicer
from host_agent.idempotency_store import (
    already_processed,
    clear_idempotency_store,
    mark_processed,
)
from libs.db_models.database import Base
from libs.db_models.host_models import (
    CommandStatus,
    CommandType,
    Host,
    HostCommand,
    HostStatus,
    OSType,
)
from libs.db_models.marketplace_models import Listing, ListingStatus, ResourceType
from libs.db_models.provisioning_models import Instance, InstanceStatus
from libs.db_models.user_models import User, UserRole
from services.provisioning_service.host_commands import (
    CommandResult,
    send_launch_command,
    send_stop_command,
    send_terminate_command,
)

# ── DB fixture ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_COMMAND_TABLES = [
    User.__table__,
    Host.__table__,
    Listing.__table__,
    Instance.__table__,
    HostCommand.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        for table in reversed(_COMMAND_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in _COMMAND_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_COMMAND_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    clear_idempotency_store()
    yield
    async with _engine.begin() as conn:
        for table in reversed(_COMMAND_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


# ── Shared seed fixture ───────────────────────────────────────────────────

@pytest_asyncio.fixture
async def seeded_entities(db: AsyncSession):
    user = User(
        id=uuid.uuid4(),
        email="dev@kynetic.test",
        hashed_password="pw",
        role=UserRole.DEVELOPER,
        is_active=True,
    )
    host = Host(
        id=uuid.uuid4(),
        user_id=user.id,
        status=HostStatus.VERIFIED,
        os_type=OSType.LINUX,
        agent_version="1.0.0",
    )
    listing = Listing(
        id=uuid.uuid4(),
        host_id=host.id,
        owner_user_id=user.id,
        resource_type=ResourceType.gpu,
        price_per_hour_usd=1.0,
        price_per_hour_inr=83.0,
        price_per_second_usd=0.000277,
        price_per_second_inr=0.023,
        status=ListingStatus.active,
    )
    instance = Instance(
        id=uuid.uuid4(),
        developer_id=user.id,
        listing_id=listing.id,
        host_id=host.id,
        status=InstanceStatus.pending,
        hold_amount=1.0,
        price_per_second_usd=0.000277,
    )
    async with db.begin():
        db.add_all([user, host, listing, instance])

    return {"user": user, "host": host, "listing": listing, "instance": instance}


# ── Idempotency Store Tests ───────────────────────────────────────────────

def test_idempotency_store_behavior():
    key = "test-key-123"
    assert not already_processed(key)
    mark_processed(key)
    assert already_processed(key)
    clear_idempotency_store()
    assert not already_processed(key)


# ── Host Commands Tests ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_launch_command_success(db: AsyncSession, seeded_entities):
    e = seeded_entities
    res: CommandResult = await send_launch_command(
        db,
        host_id=e["host"].id,
        instance_id=e["instance"].id,
        image="ubuntu:latest",
    )

    assert res.success is True
    assert "Launched VM" in res.message
    assert res.idempotency_key is not None

    # Verify audit row in DB
    result = await db.execute(
        select(HostCommand).where(HostCommand.idempotency_key == res.idempotency_key)
    )
    cmd_row = result.scalar_one_or_none()
    assert cmd_row is not None
    assert cmd_row.command_type == CommandType.LAUNCH
    assert cmd_row.status == CommandStatus.ACKED
    assert cmd_row.acked_at is not None


@pytest.mark.asyncio
async def test_send_stop_command_success(db: AsyncSession, seeded_entities):
    e = seeded_entities
    res: CommandResult = await send_stop_command(
        db,
        host_id=e["host"].id,
        instance_id=e["instance"].id,
    )

    assert res.success is True
    assert res.message == "Stopped"

    # Verify audit row
    result = await db.execute(
        select(HostCommand).where(HostCommand.idempotency_key == res.idempotency_key)
    )
    cmd_row = result.scalar_one_or_none()
    assert cmd_row is not None
    assert cmd_row.command_type == CommandType.STOP
    assert cmd_row.status == CommandStatus.ACKED


@pytest.mark.asyncio
async def test_send_terminate_command_success(db: AsyncSession, seeded_entities):
    e = seeded_entities
    res: CommandResult = await send_terminate_command(
        db,
        host_id=e["host"].id,
        instance_id=e["instance"].id,
    )

    assert res.success is True
    assert res.message == "Terminated"

    # Verify audit row
    result = await db.execute(
        select(HostCommand).where(HostCommand.idempotency_key == res.idempotency_key)
    )
    cmd_row = result.scalar_one_or_none()
    assert cmd_row is not None
    assert cmd_row.command_type == CommandType.TERMINATE
    assert cmd_row.status == CommandStatus.ACKED


@pytest.mark.asyncio
async def test_idempotent_replay_prevention():
    """Verify that replaying a command with the same idempotency key is detected."""
    servicer = HostAgentCommandServicer()
    key = "unique-idempotency-key-001"

    req = type("Req", (), {
        "instance_id": str(uuid.uuid4()),
        "idempotency_key": key,
        "template_id": "",
        "image": "python:3.11",
    })()

    # First launch -> real launch
    res1 = await servicer.Launch(req)
    assert res1["success"] is True
    assert "Launched VM" in res1["message"]

    # Replay launch -> idempotent response
    res2 = await servicer.Launch(req)
    assert res2["success"] is True
    assert "Already processed" in res2["message"]


@pytest.mark.asyncio
async def test_command_failure_logged_in_audit_table(db: AsyncSession, seeded_entities):
    e = seeded_entities

    with patch.object(
        HostAgentCommandServicer,
        "Launch",
        side_effect=RuntimeError("Docker engine down"),
    ):
        res: CommandResult = await send_launch_command(
            db,
            host_id=e["host"].id,
            instance_id=e["instance"].id,
        )

        assert res.success is False
        assert "Docker engine down" in res.message

        result = await db.execute(
            select(HostCommand).where(HostCommand.idempotency_key == res.idempotency_key)
        )
        cmd_row = result.scalar_one_or_none()
        assert cmd_row is not None
        assert cmd_row.status == CommandStatus.FAILED
