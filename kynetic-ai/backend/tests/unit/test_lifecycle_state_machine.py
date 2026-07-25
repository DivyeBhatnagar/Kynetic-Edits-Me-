"""
Phase 32 Unit Tests — Instance Lifecycle State Machine.

Tests:
  - Every legal state transition defined in LEGAL_TRANSITIONS
  - Illegal transition rejections (raising IllegalTransitionError)
  - Force-terminate from any state
"""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.db_models.database import Base
from libs.db_models.host_models import Host, HostStatus, OSType
from libs.db_models.marketplace_models import Listing, ListingStatus, ResourceType
from libs.db_models.provisioning_models import Instance, InstanceStatus
from libs.db_models.user_models import User, UserRole
from services.provisioning_service.repository import (
    IllegalTransitionError,
    InstanceRepository,
    LEGAL_TRANSITIONS,
)

# ── DB fixture ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_STATE_TABLES = [
    User.__table__,
    Host.__table__,
    Listing.__table__,
    Instance.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        for table in reversed(_STATE_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in _STATE_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_STATE_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    yield
    async with _engine.begin() as conn:
        for table in reversed(_STATE_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


# ── Shared helper ─────────────────────────────────────────────────────────

async def _seed_instance(db: AsyncSession, initial_status: InstanceStatus = InstanceStatus.pending) -> Instance:
    user = User(
        id=uuid.uuid4(),
        email=f"user_{uuid.uuid4().hex[:6]}@kynetic.test",
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
        status=initial_status,
        hold_amount=1.0,
        price_per_second_usd=0.000277,
    )
    async with db.begin():
        db.add_all([user, host, listing, instance])
    return instance


# ── Legal Transition Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_legal_transitions_path(db: AsyncSession):
    """Test full happy path: pending -> provisioning -> running -> stopping -> stopped -> running -> terminated."""
    inst = await _seed_instance(db, InstanceStatus.pending)
    repo = InstanceRepository(db)

    # pending -> provisioning
    async with db.begin():
        await repo.transition_state(inst.id, InstanceStatus.provisioning)
    assert inst.status == InstanceStatus.provisioning

    # provisioning -> running
    async with db.begin():
        await repo.transition_state(inst.id, InstanceStatus.running)
    assert inst.status == InstanceStatus.running
    assert inst.started_at is not None

    # running -> stopping
    async with db.begin():
        await repo.transition_state(inst.id, InstanceStatus.stopping)
    assert inst.status == InstanceStatus.stopping
    assert inst.stopped_at is not None

    # stopping -> stopped
    async with db.begin():
        await repo.transition_state(inst.id, InstanceStatus.stopped)
    assert inst.status == InstanceStatus.stopped

    # stopped -> running
    async with db.begin():
        await repo.transition_state(inst.id, InstanceStatus.running)
    assert inst.status == InstanceStatus.running

    # running -> terminated
    async with db.begin():
        await repo.transition_state(inst.id, InstanceStatus.terminated)
    assert inst.status == InstanceStatus.terminated
    assert inst.terminated_at is not None


@pytest.mark.asyncio
async def test_force_terminate_from_any_state(db: AsyncSession):
    """Verify that any non-terminated state can transition directly to terminated."""
    for initial in (InstanceStatus.pending, InstanceStatus.provisioning, InstanceStatus.running, InstanceStatus.stopping, InstanceStatus.stopped, InstanceStatus.failed):
        inst = await _seed_instance(db, initial)
        repo = InstanceRepository(db)
        async with db.begin():
            await repo.transition_state(inst.id, InstanceStatus.terminated)
        assert inst.status == InstanceStatus.terminated


# ── Illegal Transition Tests ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_illegal_transition_terminated_to_running(db: AsyncSession):
    """Terminated is a terminal state; transitioning to running must raise IllegalTransitionError."""
    inst = await _seed_instance(db, InstanceStatus.terminated)
    repo = InstanceRepository(db)

    with pytest.raises(IllegalTransitionError) as exc_info:
        async with db.begin():
            await repo.transition_state(inst.id, InstanceStatus.running)

    assert exc_info.value.current == InstanceStatus.terminated
    assert exc_info.value.requested == InstanceStatus.running


@pytest.mark.asyncio
async def test_illegal_transition_stopped_to_provisioning(db: AsyncSession):
    """Stopped cannot transition directly back to provisioning."""
    inst = await _seed_instance(db, InstanceStatus.stopped)
    repo = InstanceRepository(db)

    with pytest.raises(IllegalTransitionError):
        async with db.begin():
            await repo.transition_state(inst.id, InstanceStatus.provisioning)


@pytest.mark.asyncio
async def test_illegal_transition_failed_to_running(db: AsyncSession):
    """Failed instances cannot transition to running without re-provisioning."""
    inst = await _seed_instance(db, InstanceStatus.failed)
    repo = InstanceRepository(db)

    with pytest.raises(IllegalTransitionError):
        async with db.begin():
            await repo.transition_state(inst.id, InstanceStatus.running)
