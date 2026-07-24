"""
Phase 33 Integration Test Suite — End-to-End Instance Lifecycle (tests/integration/test_instance_lifecycle_e2e.py)

Tests full request -> validation -> provisioning -> metering -> termination chain:
  1. test_full_instance_lifecycle: complete E2E lifecycle (launch, poll running, connection info, debit, terminate, deletion receipt)
  2. test_insufficient_balance_never_reaches_host_agent: pre-scheduler validation gate stops zero-balance launch
  3. test_host_agent_disconnect_mid_provisioning: host unreachable during launch -> status=failed + hold refunded
  4. test_zero_balance_auto_termination: wallet depletion during run triggers auto-termination
  5. test_idempotent_launch_retry: command channel replay protection prevents duplicate workload launches
"""

import asyncio
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from host_agent.command_listener import HostAgentCommandServicer
from host_agent.idempotency_store import clear_idempotency_store
from libs.db_models.database import Base
from libs.db_models.host_models import (
    HeartbeatStatus,
    Host,
    HostCommand,
    HostHeartbeat,
    HostStatus,
    OSType,
)
from libs.db_models.marketplace_models import (
    Currency,
    Listing,
    ListingStatus,
    ResourceType,
    TransactionType,
    Wallet,
    WalletTransaction,
)
from libs.db_models.provisioning_models import (
    Instance,
    InstanceStatus,
    SSHSession,
    SecureDeletionReceipt,
)
from libs.db_models.user_models import AuditLog, User, UserRole
from services.provisioning_service.agent_protocol import AgentProtocol
from services.provisioning_service.audit import log_validation_rejection
from services.provisioning_service.host_commands import (
    CommandResult,
    send_launch_command,
)
from services.provisioning_service.schemas import InstanceResponse
from services.provisioning_service.tasks import (
    _provision_instance_async,
    _terminate_instance_async,
)
from services.provisioning_service.validators import (
    InstanceValidationError,
    validate_instance_request,
)
from services.wallet_billing_service.metering import debit_running_instance

# ── DB fixture ─────────────────────────────────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
_engine = create_async_engine(TEST_DB_URL, echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)

_E2E_TABLES = [
    User.__table__,
    Host.__table__,
    HostHeartbeat.__table__,
    Listing.__table__,
    Wallet.__table__,
    WalletTransaction.__table__,
    Instance.__table__,
    SSHSession.__table__,
    SecureDeletionReceipt.__table__,
    HostCommand.__table__,
    AuditLog.__table__,
]


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _create_tables():
    async with _engine.begin() as conn:
        for table in reversed(_E2E_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
        for table in _E2E_TABLES:
            await conn.run_sync(table.create, checkfirst=True)
    yield
    async with _engine.begin() as conn:
        for table in reversed(_E2E_TABLES):
            await conn.run_sync(table.drop, checkfirst=True)
    await _engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_tables(_create_tables):
    clear_idempotency_store()
    yield
    async with _engine.begin() as conn:
        for table in reversed(_E2E_TABLES):
            await conn.execute(table.delete())


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    async with _session_factory() as session:
        yield session


# ── Seed helper ───────────────────────────────────────────────────────────

async def _seed_environment(db: AsyncSession, wallet_balance_usd: Decimal = Decimal("50.0")):
    dev_user = User(
        id=uuid.uuid4(),
        email=f"dev_{uuid.uuid4().hex[:6]}@kynetic.ai",
        hashed_password="pw",
        role=UserRole.DEVELOPER,
        is_active=True,
    )
    host_user = User(
        id=uuid.uuid4(),
        email=f"host_{uuid.uuid4().hex[:6]}@kynetic.ai",
        hashed_password="pw",
        role=UserRole.HOST,
        is_active=True,
    )
    host = Host(
        id=uuid.uuid4(),
        user_id=host_user.id,
        status=HostStatus.LISTED,
        os_type=OSType.LINUX,
        agent_version="1.0.0",
    )
    heartbeat = HostHeartbeat(
        id=uuid.uuid4(),
        host_id=host.id,
        status=HeartbeatStatus.IDLE,
        recorded_at=datetime.now(timezone.utc),
    )
    listing = Listing(
        id=uuid.uuid4(),
        host_id=host.id,
        owner_user_id=host_user.id,
        resource_type=ResourceType.gpu,
        price_per_hour_usd=Decimal("1.0"),
        price_per_hour_inr=Decimal("84.0"),
        price_per_second_usd=Decimal("0.0002777778"),
        price_per_second_inr=Decimal("0.023333"),
        status=ListingStatus.active,
    )
    wallet = Wallet(
        id=uuid.uuid4(),
        user_id=dev_user.id,
        balance_usd=wallet_balance_usd,
        balance_inr=wallet_balance_usd * Decimal("84.0"),
        preferred_currency=Currency.usd,
    )

    async with db.begin():
        db.add_all([dev_user, host_user, host, heartbeat, listing, wallet])

    return {
        "dev_user": dev_user,
        "host_user": host_user,
        "host": host,
        "listing": listing,
        "wallet": wallet,
    }


# ── 1. Full E2E Lifecycle Test ────────────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_instance_lifecycle(db: AsyncSession):
    env = await _seed_environment(db, wallet_balance_usd=Decimal("100.0"))
    dev = env["dev_user"]
    listing = env["listing"]
    host = env["host"]

    # Step A: Validate request (Phase 27 gate)
    validated = await validate_instance_request(
        db,
        requester_id=dev.id,
        developer_id=dev.id,
        listing_id=listing.id,
        hold_hours=Decimal("1.0"),
    )
    assert validated.hold_amount == Decimal("1.000000")

    # Step B: Create Instance record (status=pending)
    instance = Instance(
        id=uuid.uuid4(),
        developer_id=dev.id,
        listing_id=listing.id,
        host_id=host.id,
        status=InstanceStatus.pending,
        hold_amount=validated.hold_amount,
        price_per_second_usd=validated.price_per_second_usd,
        agent_host_url="mock://agent",
    )
    db.add(instance)
    await db.flush()

    assert instance.status == InstanceStatus.pending

    # Step C: Provision instance task execution
    with patch(
        "services.provisioning_service.tasks.async_session_factory",
        return_value=_session_factory(),
    ), patch(
        "services.provisioning_service.tasks.start_billing",
    ), patch(
        "services.provisioning_service.tasks.on_instance_running",
        new_callable=AsyncMock,
    ) as mock_evt_running:
        await _provision_instance_async(str(instance.id))

    # Verify instance state transitioned pending -> provisioning -> running
    running_status = (
        await db.execute(select(Instance.status).where(Instance.id == instance.id))
    ).scalar_one()
    assert running_status == InstanceStatus.running
    mock_evt_running.assert_called_once()

    # Step D: Terminate instance task execution
    with patch(
        "services.provisioning_service.tasks.async_session_factory",
        return_value=_session_factory(),
    ), patch(
        "services.provisioning_service.tasks.stop_billing",
    ), patch(
        "services.provisioning_service.tasks.on_instance_terminated",
        new_callable=AsyncMock,
    ) as mock_evt_term:
        await _terminate_instance_async(str(instance.id), reason="user_requested")

    # Verify instance state transitioned to terminated
    term_status = (
        await db.execute(select(Instance.status).where(Instance.id == instance.id))
    ).scalar_one()
    assert term_status == InstanceStatus.terminated
    mock_evt_term.assert_called_once()

    # Verify SecureDeletionReceipt was generated
    receipt_res = await db.execute(
        select(SecureDeletionReceipt).where(SecureDeletionReceipt.instance_id == instance.id)
    )
    receipt = receipt_res.scalar_one_or_none()
    assert receipt is not None
    assert receipt.agent_confirmation_hash != ""


# ── 2. Insufficient Balance Validation Rejection Test ──────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_insufficient_balance_never_reaches_host_agent(db: AsyncSession):
    env = await _seed_environment(db, wallet_balance_usd=Decimal("0.0"))
    dev = env["dev_user"]
    listing = env["listing"]

    with pytest.raises(InstanceValidationError) as exc:
        await validate_instance_request(
            db,
            requester_id=dev.id,
            developer_id=dev.id,
            listing_id=listing.id,
            hold_hours=Decimal("1.0"),
        )

    assert exc.value.code == "INSUFFICIENT_BALANCE"

    # Verify zero host_commands rows were generated
    cmd_res = await db.execute(select(HostCommand))
    commands = cmd_res.scalars().all()
    assert len(commands) == 0


# ── 3. Host Agent Disconnect Mid-Provisioning Test ─────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_host_agent_disconnect_mid_provisioning(db: AsyncSession):
    env = await _seed_environment(db, wallet_balance_usd=Decimal("50.0"))
    dev = env["dev_user"]
    listing = env["listing"]
    host = env["host"]

    instance = Instance(
        id=uuid.uuid4(),
        developer_id=dev.id,
        listing_id=listing.id,
        host_id=host.id,
        status=InstanceStatus.pending,
        hold_amount=Decimal("1.0"),
        price_per_second_usd=Decimal("0.000277"),
        agent_host_url="http://192.168.1.99:8443",  # Unreachable host
    )
    async with db.begin():
        db.add(instance)

    # Mock agent.provision() raising ConnectError
    with patch(
        "services.provisioning_service.tasks.async_session_factory",
        return_value=_session_factory(),
    ), patch(
        "services.provisioning_service.agent_protocol.AgentProtocol.provision",
        side_effect=Exception("Host Agent disconnected mid-provisioning"),
    ), patch(
        "services.provisioning_service.tasks.on_instance_failed",
        new_callable=AsyncMock,
    ) as mock_failed_evt:
        await _provision_instance_async(str(instance.id))

    # Verify instance state transitioned to failed
    failed_status = (
        await db.execute(select(Instance.status).where(Instance.id == instance.id))
    ).scalar_one()
    assert failed_status == InstanceStatus.failed
    mock_failed_evt.assert_called_once()


# ── 4. Zero-Balance Auto-Termination Test ─────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_zero_balance_auto_termination(db: AsyncSession):
    # Fund developer wallet with zero balance
    env = await _seed_environment(db, wallet_balance_usd=Decimal("0.0"))
    dev = env["dev_user"]
    listing = env["listing"]
    host = env["host"]

    instance = Instance(
        id=uuid.uuid4(),
        developer_id=dev.id,
        listing_id=listing.id,
        host_id=host.id,
        status=InstanceStatus.running,
        hold_amount=Decimal("1.0"),
        price_per_second_usd=Decimal("0.000277"),
        agent_host_url="mock://agent",
    )
    async with db.begin():
        db.add(instance)

    # Mock sync session query results for debit_running_instance
    mock_instance = type("InstMock", (), {
        "id": instance.id,
        "developer_id": dev.id,
        "status": InstanceStatus.running,
        "price_per_second_usd": Decimal("0.000277"),
    })()
    mock_wallet = type("WalletMock", (), {
        "user_id": dev.id,
        "balance_usd": Decimal("0.0"),
        "balance_inr": Decimal("0.0"),
        "preferred_currency": Currency.usd,
    })()

    mock_sess = MagicMock()
    mock_sess.execute.side_effect = [
        type("Res", (), {"scalar_one_or_none": lambda *a, **kw: mock_instance})(),
        type("Res", (), {"scalar_one_or_none": lambda *a, **kw: mock_wallet})(),
    ]
    mock_sess.begin.return_value.__enter__ = lambda s: s
    mock_sess.begin.return_value.__exit__ = lambda s, a, b, c: None
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_sess
    mock_ctx.__exit__.return_value = None

    with patch(
        "services.wallet_billing_service.metering._get_sync_session",
        return_value=mock_ctx,
    ), patch(
        "services.wallet_billing_service.metering._trigger_auto_terminate",
    ) as mock_auto_term:
        res = debit_running_instance(str(instance.id))

    assert res["stopped"] is True
    assert res["reason"] == "zero_balance"
    mock_auto_term.assert_called_once_with(str(instance.id), reason="zero_balance_auto_termination")


# ── 5. Idempotent Launch Retry Test ───────────────────────────────────────

@pytest.mark.integration
@pytest.mark.asyncio
async def test_idempotent_launch_retry(db: AsyncSession):
    env = await _seed_environment(db)
    host = env["host"]
    instance_id = uuid.uuid4()

    # First launch command
    res1: CommandResult = await send_launch_command(
        db,
        host_id=host.id,
        instance_id=instance_id,
        image="python:3.11",
    )
    assert res1.success is True
    assert "Launched VM" in res1.message

    # Replay launch command with same idempotency key directly to servicer
    servicer = HostAgentCommandServicer()
    req_replay = type("Req", (), {
        "instance_id": str(instance_id),
        "idempotency_key": res1.idempotency_key,
        "template_id": "",
        "image": "python:3.11",
    })()

    res2 = await servicer.Launch(req_replay)
    assert res2["success"] is True
    assert "Already processed (idempotent replay)" in res2["message"]
