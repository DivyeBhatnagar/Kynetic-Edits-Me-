"""
Phase 27 Unit Tests — Business Logic Validation Layer.

Tests the `validate_instance_request()` function and its four sub-validators:
  - Permission check
  - Listing availability check
  - Host online/idle check (including heartbeat freshness)
  - Wallet balance check

All tests run against an in-memory SQLite DB (via conftest.py) — no real
Postgres or network calls required. Seeded fixtures provide the DB rows.

Coverage target: 100% of validators.py lines (enforced in CI via
`--cov-fail-under=90` on this module).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import libs.db_models  # noqa: F401
from libs.db_models.host_models import Host, HostHeartbeat, HeartbeatStatus, HostStatus, OSType
from libs.db_models.marketplace_models import (
    Currency,
    Listing,
    ListingStatus,
    ResourceType,
    Wallet,
)
from libs.db_models.user_models import User, UserRole
from libs.db_models.database import Base
from services.provisioning_service.validators import (
    InstanceValidationError,
    validate_instance_request,
    HEARTBEAT_STALENESS_SECONDS,
)

# ── In-memory test database ────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

# Only the tables used by the validator — avoids broken FKs in other models.
_VALIDATOR_TABLES = [
    User.__table__,
    Host.__table__,
    HostHeartbeat.__table__,
    Listing.__table__,
    Wallet.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    """Create only the tables needed by validators — no full-schema create_all."""
    async with _engine.begin() as conn:
        # Drop in reverse dependency order (safe on empty DB)
        for table in reversed(_VALIDATOR_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        # Create in dependency order
        for table in _VALIDATOR_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_VALIDATOR_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    """Truncate only the validator test tables between tests."""
    yield
    async with _engine.begin() as conn:
        for table in reversed(_VALIDATOR_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Fresh DB session per test."""
    async with _session_factory() as session:
        yield session


# ── Shared seed helpers ────────────────────────────────────────────────────

def _make_user(
    role: UserRole = UserRole.DEVELOPER,
    user_id: uuid.UUID | None = None,
) -> User:
    return User(
        id=user_id or uuid.uuid4(),
        email=f"user_{uuid.uuid4().hex[:6]}@kynetic.test",
        hashed_password="$2b$12$placeholder",
        role=role,
        is_active=True,
    )


def _make_host(
    status: HostStatus = HostStatus.VERIFIED,
    host_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> Host:
    return Host(
        id=host_id or uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        status=status,
        os_type=OSType.LINUX,
        agent_version="1.0.0",
    )


def _make_heartbeat(
    host_id: uuid.UUID,
    status: HeartbeatStatus = HeartbeatStatus.IDLE,
    age_seconds: float = 10.0,
) -> HostHeartbeat:
    recorded = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return HostHeartbeat(
        id=uuid.uuid4(),
        host_id=host_id,
        status=status,
        recorded_at=recorded,
    )


def _make_listing(
    host_id: uuid.UUID,
    status: ListingStatus = ListingStatus.active,
    is_available: bool = True,
    price_usd: Decimal = Decimal("1.000000"),
    price_inr: Decimal = Decimal("83.000000"),
    listing_id: uuid.UUID | None = None,
    owner_user_id: uuid.UUID | None = None,
) -> Listing:
    return Listing(
        id=listing_id or uuid.uuid4(),
        host_id=host_id,
        owner_user_id=owner_user_id or uuid.uuid4(),
        resource_type=ResourceType.gpu,
        price_per_hour_usd=price_usd,
        price_per_hour_inr=price_inr,
        price_per_second_usd=(price_usd / Decimal("3600")).quantize(Decimal("0.0000000001")),
        price_per_second_inr=(price_inr / Decimal("3600")).quantize(Decimal("0.0000000001")),
        status=status,
    )


def _make_wallet(
    user_id: uuid.UUID,
    balance_usd: Decimal = Decimal("100.000000"),
    balance_inr: Decimal = Decimal("8300.000000"),
    preferred_currency: Currency = Currency.usd,
) -> Wallet:
    return Wallet(
        id=uuid.uuid4(),
        user_id=user_id,
        balance_usd=balance_usd,
        balance_inr=balance_inr,
        preferred_currency=preferred_currency,
    )


# ── Fixture: fully valid scenario ─────────────────────────────────────────

@pytest_asyncio.fixture
async def valid_scenario(db: AsyncSession):
    """Seed a complete, valid scenario: funded developer, active listing, idle verified host."""
    developer = _make_user(UserRole.DEVELOPER)
    host_user = _make_user(UserRole.HOST)
    host = _make_host(HostStatus.VERIFIED, user_id=host_user.id)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE, age_seconds=10)
    listing = _make_listing(host.id, ListingStatus.active, owner_user_id=host_user.id)
    wallet = _make_wallet(developer.id, balance_usd=Decimal("100.000000"))

    async with db.begin():
        db.add_all([developer, host_user, host, heartbeat, listing, wallet])

    return {
        "developer": developer,
        "host": host,
        "listing": listing,
        "wallet": wallet,
    }


# ══════════════════════════════════════════════════════════════════════════
# Test: Happy path
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_valid_request_returns_validated_object(db: AsyncSession, valid_scenario):
    """A fully-valid request must succeed and return a ValidatedInstanceRequest."""
    s = valid_scenario
    result = await validate_instance_request(
        db,
        requester_id=str(s["developer"].id),
        developer_id=str(s["developer"].id),
        listing_id=str(s["listing"].id),
        hold_hours=Decimal("1"),
    )

    assert result.developer_id == str(s["developer"].id)
    assert result.listing_id == str(s["listing"].id)
    assert result.host_id == str(s["host"].id)
    assert result.hold_amount > 0
    assert result.hold_currency is Currency.usd


@pytest.mark.asyncio
async def test_hold_amount_is_hourly_rate_times_hours(db: AsyncSession, valid_scenario):
    """hold_amount must equal price_per_hour * hold_hours."""
    s = valid_scenario
    listing = s["listing"]
    hours = Decimal("2")

    result = await validate_instance_request(
        db,
        requester_id=str(s["developer"].id),
        developer_id=str(s["developer"].id),
        listing_id=str(listing.id),
        hold_hours=hours,
    )

    expected = (listing.price_per_hour_usd * hours).quantize(Decimal("0.000001"))
    assert result.hold_amount == expected


# ══════════════════════════════════════════════════════════════════════════
# Test: Wallet validation
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rejects_when_wallet_missing(db: AsyncSession):
    """A developer with no wallet gets WALLET_NOT_FOUND."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE)
    listing = _make_listing(host.id, ListingStatus.active)
    # No wallet seeded

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "WALLET_NOT_FOUND"


@pytest.mark.asyncio
async def test_rejects_insufficient_usd_balance(db: AsyncSession):
    """A developer whose USD balance < hold_amount gets INSUFFICIENT_BALANCE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE)
    listing = _make_listing(host.id, price_usd=Decimal("10.000000"))  # $10/hr
    wallet = _make_wallet(developer.id, balance_usd=Decimal("0.000001"))  # nearly empty

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "INSUFFICIENT_BALANCE"
    assert "Required" in exc_info.value.message


@pytest.mark.asyncio
async def test_accepts_exact_balance_match(db: AsyncSession):
    """A wallet with exactly the required hold amount must succeed (not reject)."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE)
    listing = _make_listing(host.id, price_usd=Decimal("1.000000"))  # $1/hr, $1.000000 hold
    wallet = _make_wallet(developer.id, balance_usd=Decimal("1.000000"))

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing, wallet])

    # Should NOT raise
    result = await validate_instance_request(
        db,
        requester_id=str(developer.id),
        developer_id=str(developer.id),
        listing_id=str(listing.id),
        hold_hours=Decimal("1"),
    )
    assert result.hold_amount == Decimal("1.000000")


# ══════════════════════════════════════════════════════════════════════════
# Test: Listing validation
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rejects_unknown_listing(db: AsyncSession):
    """A non-existent listing_id gets LISTING_NOT_FOUND."""
    developer = _make_user(UserRole.DEVELOPER)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(uuid.uuid4()),  # nonexistent
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "LISTING_NOT_FOUND"


@pytest.mark.asyncio
async def test_rejects_paused_listing(db: AsyncSession):
    """A paused listing gets LISTING_UNAVAILABLE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    listing = _make_listing(host.id, status=ListingStatus.paused)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "LISTING_UNAVAILABLE"
    assert "paused" in exc_info.value.message


@pytest.mark.asyncio
async def test_rejects_delisted_listing(db: AsyncSession):
    """A delisted listing gets LISTING_UNAVAILABLE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    listing = _make_listing(host.id, status=ListingStatus.delisted)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "LISTING_UNAVAILABLE"


# ══════════════════════════════════════════════════════════════════════════
# Test: Host validation
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rejects_suspended_host(db: AsyncSession):
    """A suspended host gets HOST_NOT_VERIFIED."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.SUSPENDED)
    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "HOST_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_rejects_pending_verification_host(db: AsyncSession):
    """A host still in pending_verification gets HOST_NOT_VERIFIED."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.PENDING_VERIFICATION)
    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "HOST_NOT_VERIFIED"


@pytest.mark.asyncio
async def test_accepts_listed_host(db: AsyncSession):
    """A LISTED host (verified + has a listing) is eligible and must succeed."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.LISTED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE, age_seconds=5)
    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing, wallet])

    result = await validate_instance_request(
        db,
        requester_id=str(developer.id),
        developer_id=str(developer.id),
        listing_id=str(listing.id),
        hold_hours=Decimal("1"),
    )
    assert result.host_id == str(host.id)


@pytest.mark.asyncio
async def test_rejects_host_with_no_heartbeat(db: AsyncSession):
    """A host that has never sent a heartbeat gets HOST_NOT_IDLE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    # NO heartbeat added
    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "HOST_NOT_IDLE"
    assert "never sent" in exc_info.value.message


@pytest.mark.asyncio
async def test_rejects_stale_heartbeat(db: AsyncSession):
    """A heartbeat older than HEARTBEAT_STALENESS_SECONDS gets HOST_NOT_IDLE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    # Heartbeat is stale — past the threshold
    stale_hb = _make_heartbeat(
        host.id,
        HeartbeatStatus.IDLE,
        age_seconds=HEARTBEAT_STALENESS_SECONDS + 10,
    )
    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, stale_hb, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "HOST_NOT_IDLE"
    assert "offline" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_rejects_busy_host(db: AsyncSession):
    """A host whose latest heartbeat reports BUSY gets HOST_NOT_IDLE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.BUSY, age_seconds=5)
    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "HOST_NOT_IDLE"
    assert "busy" in exc_info.value.message.lower()


@pytest.mark.asyncio
async def test_uses_most_recent_heartbeat(db: AsyncSession):
    """Only the most recent heartbeat matters — old stale one is ignored."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)

    # Older heartbeat: stale and BUSY
    old_hb = _make_heartbeat(
        host.id,
        HeartbeatStatus.BUSY,
        age_seconds=HEARTBEAT_STALENESS_SECONDS + 60,
    )
    # Newer heartbeat: fresh and IDLE
    fresh_hb = _make_heartbeat(host.id, HeartbeatStatus.IDLE, age_seconds=5)

    listing = _make_listing(host.id, ListingStatus.active)
    wallet = _make_wallet(developer.id)

    async with db.begin():
        db.add_all([developer, host, old_hb, fresh_hb, listing, wallet])

    # Should succeed (fresh IDLE heartbeat wins)
    result = await validate_instance_request(
        db,
        requester_id=str(developer.id),
        developer_id=str(developer.id),
        listing_id=str(listing.id),
        hold_hours=Decimal("1"),
    )
    assert result.host_id == str(host.id)


# ══════════════════════════════════════════════════════════════════════════
# Test: Permission validation
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_rejects_unauthorized_third_party(db: AsyncSession, valid_scenario):
    """A non-admin user acting for another developer gets PERMISSION_DENIED."""
    s = valid_scenario
    # Create an attacker — a regular developer, not an admin
    attacker = _make_user(UserRole.DEVELOPER)
    attacker_wallet = _make_wallet(attacker.id, balance_usd=Decimal("100.000000"))

    async with db.begin():
        db.add_all([attacker, attacker_wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(attacker.id),       # attacker requests
            developer_id=str(s["developer"].id),  # for victim's account
            listing_id=str(s["listing"].id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_admin_can_act_for_developer(db: AsyncSession, valid_scenario):
    """An admin user may provision instances on behalf of any developer."""
    s = valid_scenario
    admin = _make_user(UserRole.ADMIN)

    async with db.begin():
        db.add(admin)

    # Admin acting for the developer — must succeed
    result = await validate_instance_request(
        db,
        requester_id=str(admin.id),
        developer_id=str(s["developer"].id),
        listing_id=str(s["listing"].id),
        hold_hours=Decimal("1"),
    )
    assert result.developer_id == str(s["developer"].id)


@pytest.mark.asyncio
async def test_rejects_nonexistent_requester(db: AsyncSession, valid_scenario):
    """A requester that doesn't exist in the DB gets PERMISSION_DENIED."""
    s = valid_scenario
    ghost_id = str(uuid.uuid4())

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=ghost_id,
            developer_id=str(s["developer"].id),
            listing_id=str(s["listing"].id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "PERMISSION_DENIED"


# ══════════════════════════════════════════════════════════════════════════
# Test: INR-preferred wallet
# ══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_uses_inr_for_inr_preferred_developer(db: AsyncSession):
    """A developer with preferred_currency=INR gets hold computed in INR."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE)
    listing = _make_listing(
        host.id,
        price_usd=Decimal("1.000000"),
        price_inr=Decimal("83.000000"),
    )
    # INR-preferred wallet with enough INR
    wallet = _make_wallet(
        developer.id,
        balance_usd=Decimal("0.000001"),  # nearly empty USD
        balance_inr=Decimal("200.000000"),  # enough INR
        preferred_currency=Currency.inr,
    )

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing, wallet])

    result = await validate_instance_request(
        db,
        requester_id=str(developer.id),
        developer_id=str(developer.id),
        listing_id=str(listing.id),
        hold_hours=Decimal("1"),
    )

    assert result.hold_currency is Currency.inr
    assert result.hold_amount == Decimal("83.000000")


@pytest.mark.asyncio
async def test_rejects_inr_developer_with_insufficient_inr(db: AsyncSession):
    """An INR-preferred developer with insufficient INR gets INSUFFICIENT_BALANCE."""
    developer = _make_user(UserRole.DEVELOPER)
    host = _make_host(HostStatus.VERIFIED)
    heartbeat = _make_heartbeat(host.id, HeartbeatStatus.IDLE)
    listing = _make_listing(host.id, price_inr=Decimal("83.000000"))
    wallet = _make_wallet(
        developer.id,
        balance_usd=Decimal("999.000000"),   # plenty of USD
        balance_inr=Decimal("0.000001"),     # nearly empty INR
        preferred_currency=Currency.inr,
    )

    async with db.begin():
        db.add_all([developer, host, heartbeat, listing, wallet])

    with pytest.raises(InstanceValidationError) as exc_info:
        await validate_instance_request(
            db,
            requester_id=str(developer.id),
            developer_id=str(developer.id),
            listing_id=str(listing.id),
            hold_hours=Decimal("1"),
        )

    assert exc_info.value.code == "INSUFFICIENT_BALANCE"
    assert "INR" in exc_info.value.message


# ══════════════════════════════════════════════════════════════════════════
# Test: InstanceValidationError attributes
# ══════════════════════════════════════════════════════════════════════════

def test_validation_error_stores_code_and_message():
    """InstanceValidationError.code and .message are accessible on the exception."""
    err = InstanceValidationError("SOME_CODE", "Some human-readable message.")
    assert err.code == "SOME_CODE"
    assert err.message == "Some human-readable message."
    assert str(err) == "Some human-readable message."
    assert "SOME_CODE" in repr(err)
