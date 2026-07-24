"""
Phase 32 Unit Tests — Ephemeral Storage & Cryptographic Deletion Receipts.

Tests:
  - SecureDeletionRepository create & get_by_instance
  - Deletion confirmation hash generation & verification receipt persistence
"""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.db_models.database import Base
from libs.db_models.host_models import Host, HostStatus, OSType
from libs.db_models.marketplace_models import Listing, ListingStatus, ResourceType
from libs.db_models.provisioning_models import Instance, InstanceStatus, SecureDeletionReceipt
from libs.db_models.user_models import User, UserRole
from services.provisioning_service.repository import SecureDeletionRepository

# ── DB fixture ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_DELETION_TABLES = [
    User.__table__,
    Host.__table__,
    Listing.__table__,
    Instance.__table__,
    SecureDeletionReceipt.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        for table in reversed(_DELETION_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in _DELETION_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_DELETION_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    yield
    async with _engine.begin() as conn:
        for table in reversed(_DELETION_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_secure_deletion_receipt_repository(db: AsyncSession):
    # Seed instance
    user = User(id=uuid.uuid4(), email="dev@test.com", hashed_password="pw", role=UserRole.DEVELOPER)
    host = Host(id=uuid.uuid4(), user_id=user.id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    listing = Listing(id=uuid.uuid4(), host_id=host.id, owner_user_id=user.id, resource_type=ResourceType.gpu, price_per_hour_usd=1.0, price_per_hour_inr=83.0, price_per_second_usd=0.000277, price_per_second_inr=0.023, status=ListingStatus.active)
    instance = Instance(id=uuid.uuid4(), developer_id=user.id, listing_id=listing.id, host_id=host.id, status=InstanceStatus.terminated, hold_amount=1.0, price_per_second_usd=0.000277)
    
    async with db.begin():
        db.add_all([user, host, listing, instance])

    repo = SecureDeletionRepository(db)

    # 1. Create deletion receipt
    hash_str = "a1b2c3d4e5f67890123456789abcdef0123456789abcdef0123456789abcdef0"
    async with db.begin():
        receipt = await repo.create(
            instance_id=instance.id,
            method="nvme_crypto_shred_dod_5220_22_m",
            agent_confirmation_hash=hash_str,
            agent_payload='{"instance_id": "%s", "shredded": true}' % str(instance.id),
        )

    assert receipt.instance_id == instance.id
    assert receipt.method == "nvme_crypto_shred_dod_5220_22_m"
    assert receipt.agent_confirmation_hash == hash_str

    # 2. Get receipt by instance
    fetched = await repo.get_by_instance(instance.id)
    assert fetched is not None
    assert fetched.agent_confirmation_hash == hash_str
