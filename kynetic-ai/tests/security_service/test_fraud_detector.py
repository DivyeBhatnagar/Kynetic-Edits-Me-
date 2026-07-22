"""
Tests — Fraud Detector.

Tests the pure fraud rule logic with mocked transaction payloads.
All HTTP calls to wallet_billing_service are mocked.
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SCANNER_MOCK", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key")
os.environ.setdefault("ADMIN_JWT_SECRET_KEY", "test_admin_secret")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("PROVISIONING_SERVICE_URL", "http://localhost:8005")
os.environ.setdefault("WALLET_BILLING_SERVICE_URL", "http://localhost:8004")
os.environ.setdefault("HOST_SERVICE_URL", "http://localhost:8002")


from services.security_service.fraud_detector import scan_user_for_fraud


def _ts(minutes_ago: int = 0) -> str:
    """Returns an ISO-format UTC timestamp N minutes in the past."""
    return (datetime.now(tz=timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _make_topup(amount: float, minutes_ago: int = 0) -> dict:
    return {
        "transaction_type": "topup",
        "amount": str(amount),
        "created_at": _ts(minutes_ago),
    }


def _make_debit(amount: float, minutes_ago: int = 0) -> dict:
    return {
        "transaction_type": "debit",
        "amount": str(amount),
        "created_at": _ts(minutes_ago),
    }


USER_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_fraud_mock_mode_always_clean():
    """In mock mode, scan always returns clean — no HTTP calls made."""
    result = await scan_user_for_fraud(USER_ID, "test-token")
    assert result.flagged is False
    assert result.rules_triggered == []
    assert result.details.get("mock") is True


@pytest.mark.asyncio
async def test_rapid_topup_burst_flagged():
    """4 top-ups in <10 minutes should trigger rapid_topup_burst rule."""
    transactions = [_make_topup(10.0, minutes_ago=i) for i in range(4)]

    with patch("services.security_service.fraud_detector.httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"items": transactions})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        # Temporarily disable mock mode for this test
        with patch("services.security_service.fraud_detector.settings") as ms:
            ms.scanner_mock = False
            ms.wallet_billing_service_url = "http://localhost:8004"
            ms.fraud_topup_count_threshold = 3
            ms.fraud_topup_window_minutes = 10

            result = await scan_user_for_fraud(USER_ID, "test-token")

    assert result.flagged is True
    assert "rapid_topup_burst" in result.rules_triggered
    assert result.details["rapid_topup_count"] == 4


@pytest.mark.asyncio
async def test_clean_normal_transactions():
    """Single top-up + normal spend → no fraud flag."""
    transactions = [
        _make_topup(100.0, minutes_ago=60),
        _make_debit(5.0, minutes_ago=30),
        _make_debit(3.0, minutes_ago=20),
    ]

    with patch("services.security_service.fraud_detector.httpx.AsyncClient") as mock_client_cls:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"items": transactions})
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        with patch("services.security_service.fraud_detector.settings") as ms:
            ms.scanner_mock = False
            ms.wallet_billing_service_url = "http://localhost:8004"
            ms.fraud_topup_count_threshold = 3
            ms.fraud_topup_window_minutes = 10

            result = await scan_user_for_fraud(USER_ID, "test-token")

    assert result.flagged is False
    assert result.rules_triggered == []
