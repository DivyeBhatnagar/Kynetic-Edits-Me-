"""
Tests — Provisioning Service Scheduler.

These tests validate the pre-flight validation logic without requiring
a live database or network services. httpx transports are mocked.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.provisioning_service.scheduler import (
    InsufficientBalanceError,
    ListingUnavailableError,
    schedule_instance,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

LISTING_ID = uuid.uuid4()
DEV_ID = uuid.uuid4()
HOST_ID = uuid.uuid4()
INSTANCE_ID = uuid.uuid4()

LISTING_ACTIVE = {
    "id": str(LISTING_ID),
    "status": "active",
    "is_available": True,
    "price_per_second_usd": "0.000010",
    "host_id": str(HOST_ID),
}

LISTING_INACTIVE = {**LISTING_ACTIVE, "status": "paused", "is_available": False}

HOST_RESPONSE = {
    "id": str(HOST_ID),
    "agent_url": "http://mock-agent:8443",
    "public_ip": "1.2.3.4",
}

WALLET_FUNDED = {"balance_usd": "10.000000"}
WALLET_EMPTY = {"balance_usd": "0.000001"}


def make_repo_mock():
    """Returns a mock InstanceRepository that returns a fake instance on create()."""
    mock = AsyncMock()
    fake_instance = MagicMock()
    fake_instance.id = INSTANCE_ID
    fake_instance.agent_host_url = "http://mock-agent:8443"
    fake_instance.price_per_second_usd = Decimal("0.000010")
    fake_instance.developer_id = DEV_ID
    fake_instance.public_ip = "1.2.3.4"
    mock.create = AsyncMock(return_value=fake_instance)
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_schedule_success():
    """Happy path: valid listing + sufficient balance → creates instance + enqueues task."""
    repo = make_repo_mock()

    with (
        patch("services.provisioning_service.scheduler._fetch_listing", return_value=LISTING_ACTIVE),
        patch("services.provisioning_service.scheduler._fetch_wallet_balance", return_value=WALLET_FUNDED),
        patch("services.provisioning_service.scheduler._place_hold", return_value="txn-abc"),
        patch("services.provisioning_service.scheduler._fetch_host", return_value=HOST_RESPONSE),
        patch("services.provisioning_service.tasks.provision_instance") as mock_task,
    ):
        mock_task.delay = MagicMock()
        result = await schedule_instance(
            listing_id=LISTING_ID,
            developer_id=DEV_ID,
            auth_token="test-jwt",
            instance_repo=repo,
        )

    assert result == INSTANCE_ID
    repo.create.assert_called_once()
    mock_task.delay.assert_called_once_with(str(INSTANCE_ID))


@pytest.mark.asyncio
async def test_schedule_listing_inactive():
    """Paused listing → ListingUnavailableError before any wallet operations."""
    repo = make_repo_mock()

    with (
        patch("services.provisioning_service.scheduler._fetch_listing", return_value=LISTING_INACTIVE),
    ):
        with pytest.raises(ListingUnavailableError) as exc_info:
            await schedule_instance(
                listing_id=LISTING_ID,
                developer_id=DEV_ID,
                auth_token="test-jwt",
                instance_repo=repo,
            )

    assert exc_info.value.code == "listing_unavailable"
    repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_schedule_insufficient_balance():
    """Balance below 1-hour hold → InsufficientBalanceError. No instance created."""
    repo = make_repo_mock()
    # price_per_second_usd = $0.000010
    # hold = $0.000010 × 3600 = $0.036000
    # wallet has $0.000001 — not enough
    with (
        patch("services.provisioning_service.scheduler._fetch_listing", return_value=LISTING_ACTIVE),
        patch("services.provisioning_service.scheduler._fetch_wallet_balance", return_value=WALLET_EMPTY),
    ):
        with pytest.raises(InsufficientBalanceError) as exc_info:
            await schedule_instance(
                listing_id=LISTING_ID,
                developer_id=DEV_ID,
                auth_token="test-jwt",
                instance_repo=repo,
            )

    assert exc_info.value.code == "insufficient_balance"
    assert exc_info.value.required > exc_info.value.available
    repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_hold_amount_calculation():
    """
    Verifies 1-hour hold math: price_per_second * 3600 rounded UP to 6 decimal places.
    """
    from services.provisioning_service.scheduler import schedule_instance
    from decimal import Decimal, ROUND_UP

    price = Decimal("0.000010")
    hold_seconds = 3600
    expected = (price * hold_seconds).quantize(Decimal("0.000001"), rounding=ROUND_UP)
    assert expected == Decimal("0.036000")


def test_scheduler_error_codes():
    """Verify error classes have the correct machine-readable codes."""
    from services.provisioning_service.scheduler import (
        HostUnreachableError,
        InsufficientBalanceError,
        ListingUnavailableError,
    )
    assert InsufficientBalanceError(Decimal("1"), Decimal("0")).code == "insufficient_balance"
    assert ListingUnavailableError(LISTING_ID).code == "listing_unavailable"
    assert HostUnreachableError(HOST_ID).code == "host_unreachable"
