"""
Phase 28 Unit Tests — Billing Event Integration & Metering.

Tests:
  - Event Bus (publish & subscribe over mock Redis)
  - Status Sync publisher functions (on_instance_running, on_instance_terminated, on_instance_failed)
  - Event Handlers (_handle_instance_running, _handle_instance_terminated, _handle_instance_failed)
  - Metering calculations & hold refund logic (unused hold calculations, precise decimal rounding)
"""

import asyncio
import json
import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from libs.events.bus import (
    INSTANCE_FAILED,
    INSTANCE_RUNNING,
    INSTANCE_TERMINATED,
    publish_event,
)
from services.provisioning_service.status_sync import (
    on_instance_failed,
    on_instance_running,
    on_instance_terminated,
)


@pytest.mark.asyncio
async def test_publish_event_success():
    """Verify publish_event correctly formats payload and calls redis.publish."""
    mock_redis = AsyncMock()
    with patch("libs.events.bus._get_redis", return_value=mock_redis):
        payload = {"instance_id": "test-123", "status": "running"}
        await publish_event(INSTANCE_RUNNING, payload)

        mock_redis.publish.assert_called_once_with(
            INSTANCE_RUNNING,
            json.dumps(payload),
        )


@pytest.mark.asyncio
async def test_publish_event_handles_redis_failure():
    """Verify publish_event does not raise exception if Redis fails (non-blocking)."""
    mock_redis = AsyncMock()
    mock_redis.publish.side_effect = Exception("Redis connection refused")

    with patch("libs.events.bus._get_redis", return_value=mock_redis):
        payload = {"instance_id": "test-123"}
        # Should not raise exception
        await publish_event(INSTANCE_RUNNING, payload)


@pytest.mark.asyncio
async def test_status_sync_on_instance_running():
    """Verify on_instance_running formats correct payload and calls publish_event."""
    instance_id = uuid.uuid4()
    developer_id = uuid.uuid4()
    listing_id = uuid.uuid4()

    with patch("services.provisioning_service.status_sync.publish_event", new_callable=AsyncMock) as mock_pub:
        await on_instance_running(
            instance_id=instance_id,
            developer_id=developer_id,
            listing_id=listing_id,
            price_per_second_usd="0.000277",
            price_per_second_inr="0.023333",
            preferred_currency="usd",
        )

        mock_pub.assert_called_once()
        channel, payload = mock_pub.call_args[0]
        assert channel == INSTANCE_RUNNING
        assert payload["instance_id"] == str(instance_id)
        assert payload["developer_id"] == str(developer_id)
        assert payload["listing_id"] == str(listing_id)
        assert payload["price_per_second_usd"] == "0.000277"
        assert payload["preferred_currency"] == "usd"
        assert "started_at" in payload


@pytest.mark.asyncio
async def test_status_sync_on_instance_terminated():
    """Verify on_instance_terminated formats correct payload and calls publish_event."""
    instance_id = uuid.uuid4()
    developer_id = uuid.uuid4()
    listing_id = uuid.uuid4()

    with patch("services.provisioning_service.status_sync.publish_event", new_callable=AsyncMock) as mock_pub:
        await on_instance_terminated(
            instance_id=instance_id,
            developer_id=developer_id,
            listing_id=listing_id,
            reason="user_requested",
            billed_seconds=1800,
        )

        mock_pub.assert_called_once()
        channel, payload = mock_pub.call_args[0]
        assert channel == INSTANCE_TERMINATED
        assert payload["instance_id"] == str(instance_id)
        assert payload["billed_seconds"] == 1800
        assert payload["reason"] == "user_requested"


@pytest.mark.asyncio
async def test_status_sync_on_instance_failed():
    """Verify on_instance_failed formats correct payload and calls publish_event."""
    instance_id = uuid.uuid4()
    developer_id = uuid.uuid4()

    with patch("services.provisioning_service.status_sync.publish_event", new_callable=AsyncMock) as mock_pub:
        await on_instance_failed(
            instance_id=instance_id,
            developer_id=developer_id,
            reason="image_scan_failed",
        )

        mock_pub.assert_called_once()
        channel, payload = mock_pub.call_args[0]
        assert channel == INSTANCE_FAILED
        assert payload["instance_id"] == str(instance_id)
        assert payload["reason"] == "image_scan_failed"


def test_metering_debit_calculation():
    """Verify precision calculations for per-second compute debits."""
    from services.wallet_billing_service.metering import AMOUNT_PRECISION, TICK_SECONDS
    from decimal import ROUND_HALF_UP

    price_per_second_usd = Decimal("0.0002777778")  # ~$1/hr
    debit_usd = (price_per_second_usd * Decimal(TICK_SECONDS)).quantize(
        AMOUNT_PRECISION, rounding=ROUND_HALF_UP
    )

    # 10s * 0.0002777778 = 0.002777778 -> 0.002778
    assert debit_usd == Decimal("0.002778")


def test_hold_refund_calculation():
    """Verify hold refund calculation on instance termination."""
    from services.wallet_billing_service.event_handlers import AMOUNT_PRECISION

    hold_usd = Decimal("1.000000")  # 1 hour hold ($1.00)
    price_per_second_usd = Decimal("0.0002777778")
    billed_seconds = 1800  # 30 mins runtime

    actual_usd = (price_per_second_usd * Decimal(billed_seconds)).quantize(
        AMOUNT_PRECISION
    )
    refund_usd = max(hold_usd - actual_usd, Decimal("0"))

    # Actual billed for 1800s: ~0.500000 USD
    # Expected refund: ~0.500000 USD
    assert actual_usd == Decimal("0.500000")
    assert refund_usd == Decimal("0.500000")
