"""
Phase 32 Unit Tests — Ephemeral SSH Key Management & SSHSessionRepository.

Tests:
  - Ephemeral RSA-4096 keypair generation
  - Fernet encryption and decryption of private key PEMs
  - SSHSessionRepository create, get_by_instance, and revoke
  - Key rotation deadline calculation & SSH command builder
"""

import uuid
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.db_models.database import Base
from libs.db_models.host_models import Host, HostStatus, OSType
from libs.db_models.marketplace_models import Listing, ListingStatus, ResourceType
from libs.db_models.provisioning_models import Instance, InstanceStatus, SSHSession
from libs.db_models.user_models import User, UserRole
from services.provisioning_service.repository import SSHSessionRepository
from services.provisioning_service.ssh_keys import (
    build_ssh_command,
    decrypt_private_key,
    encrypt_private_key,
    generate_keypair,
    key_expiry_time,
)

# ── DB fixture ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_SSH_TABLES = [
    User.__table__,
    Host.__table__,
    Listing.__table__,
    Instance.__table__,
    SSHSession.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        for table in reversed(_SSH_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in _SSH_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_SSH_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    yield
    async with _engine.begin() as conn:
        for table in reversed(_SSH_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


# ── SSH Keys Helper Tests ──────────────────────────────────────────────────

def test_generate_keypair():
    pub_key, priv_pem = generate_keypair()
    assert pub_key.startswith("ssh-rsa ")
    assert "BEGIN RSA PRIVATE KEY" in priv_pem or "BEGIN OPENSSH PRIVATE KEY" in priv_pem


def test_fernet_encryption_decryption():
    _, priv_pem = generate_keypair()
    encrypted = encrypt_private_key(priv_pem)
    assert encrypted != priv_pem

    decrypted = decrypt_private_key(encrypted)
    assert decrypted == priv_pem


def test_decrypt_corrupt_ciphertext_raises():
    with pytest.raises(InvalidToken):
        decrypt_private_key("gAAAAABbad_corrupt_base64_string")


def test_build_ssh_command():
    cmd1 = build_ssh_command(ssh_host="10.42.0.5", ssh_port=22)
    assert cmd1 == "ssh -i kynetic_key.pem kynetic@10.42.0.5"

    cmd2 = build_ssh_command(ssh_host="relay.kynetic.ai", ssh_port=2222, ssh_user="root")
    assert cmd2 == "ssh -i kynetic_key.pem -p 2222 root@relay.kynetic.ai"


def test_key_expiry_time():
    now = datetime.now(timezone.utc)
    expiry = key_expiry_time(now)
    assert expiry > now


# ── SSHSessionRepository Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ssh_session_repository_lifecycle(db: AsyncSession):
    # Seed instance
    user = User(id=uuid.uuid4(), email="user@test.com", hashed_password="pw", role=UserRole.DEVELOPER)
    host = Host(id=uuid.uuid4(), user_id=user.id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    listing = Listing(id=uuid.uuid4(), host_id=host.id, owner_user_id=user.id, resource_type=ResourceType.gpu, price_per_hour_usd=1.0, price_per_hour_inr=83.0, price_per_second_usd=0.000277, price_per_second_inr=0.023, status=ListingStatus.active)
    instance = Instance(id=uuid.uuid4(), developer_id=user.id, listing_id=listing.id, host_id=host.id, status=InstanceStatus.running, hold_amount=1.0, price_per_second_usd=0.000277)
    
    db.add_all([user, host, listing, instance])
    await db.flush()

    pub_key, priv_pem = generate_keypair()
    encrypted = encrypt_private_key(priv_pem)

    repo = SSHSessionRepository(db)
    
    # 1. Create SSH session
    ssh_session = await repo.create(
        instance_id=instance.id,
        public_key=pub_key,
        private_key_encrypted=encrypted,
        relay_host="relay.kynetic.ai",
        relay_port=2222,
    )
    await db.flush()

    assert ssh_session.instance_id == instance.id
    assert ssh_session.revoked_at is None

    # 2. Get by instance
    fetched = await repo.get_by_instance(instance.id)
    assert fetched is not None
    assert fetched.public_key == pub_key

    # 3. Revoke SSH session
    await repo.revoke(instance.id)
    await db.flush()

    fetched_revoked = await repo.get_by_instance(instance.id)
    assert fetched_revoked is not None
    assert fetched_revoked.private_key_encrypted is None  # Private key nulled out
    assert fetched_revoked.revoked_at is not None
