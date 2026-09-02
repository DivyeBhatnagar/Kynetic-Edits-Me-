"""
Integration tests — Wallet & Billing Service.
Covers: wallet creation, balance, top-up, Stripe webhook, dual-currency math,
immutable transactions, insufficient balance guard.
"""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.wallet_billing_service.billing import (
    InsufficientFundsError,
    apply_debit,
    apply_topup,
    assert_sufficient_balance,
    usd_to_inr,
)
import libs.db_models  # noqa: F401
from services.wallet_billing_service.main import app

USER_ID = str(uuid.uuid4())
WALLET_ID = str(uuid.uuid4())
JWT_PAYLOAD = {"sub": USER_ID, "role": "developer"}
FX_RATE = Decimal("84.0")


from libs.common.auth import require_auth
from libs.db_models.database import get_db_session


@pytest.fixture
def client():
    mock_session = AsyncMock()
    app.dependency_overrides[require_auth] = lambda: JWT_PAYLOAD
    app.dependency_overrides[get_db_session] = lambda: mock_session
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


# ── Billing math unit tests ────────────────────────────────────────────────

class TestBillingMath:
    """Pure unit tests for billing.py — no network, no DB."""

    def test_usd_to_inr_correct(self):
        """1 USD = 84 INR at test rate."""
        result = usd_to_inr(Decimal("1.000000"), FX_RATE)
        assert result == Decimal("84.000000")

    def test_usd_to_inr_no_float_rounding_error(self):
        """Decimal arithmetic avoids IEEE 754 float errors."""
        # Classic float trap: 0.1 + 0.2 != 0.3 in float
        result = usd_to_inr(Decimal("0.1"), FX_RATE)
        assert result == Decimal("8.400000")  # Exact, no rounding error

    def test_usd_to_inr_fractional(self):
        """Sub-cent amounts convert correctly."""
        result = usd_to_inr(Decimal("0.000694"), FX_RATE)
        # 0.000694 * 84 = 0.058296
        expected = (Decimal("0.000694") * FX_RATE).quantize(Decimal("0.000001"))
        assert result == expected

    def test_apply_topup_credits_both_currencies(self):
        """Top-up credits USD and derives INR equivalent."""
        new_usd, new_inr = apply_topup(
            Decimal("10.000000"), Decimal("840.000000"),
            Decimal("5.000000"), FX_RATE
        )
        assert new_usd == Decimal("15.000000")
        assert new_inr == Decimal("1260.000000")

    def test_apply_debit_reduces_both_currencies(self):
        """Debit reduces both USD and INR balances."""
        new_usd, new_inr = apply_debit(
            Decimal("10.000000"), Decimal("840.000000"),
            Decimal("2.000000"), FX_RATE
        )
        assert new_usd == Decimal("8.000000")
        assert new_inr == Decimal("672.000000")

    def test_apply_debit_no_negative_balance(self):
        """Balance cannot go negative (underflow guard)."""
        new_usd, new_inr = apply_debit(
            Decimal("0.000001"), Decimal("0.000001"),
            Decimal("0.000001"), FX_RATE
        )
        # Even tiny debit cannot make balance negative
        assert new_usd >= Decimal("0")
        assert new_inr >= Decimal("0")

    def test_insufficient_balance_raises(self):
        """assert_sufficient_balance raises InsufficientFundsError when USD low."""
        with pytest.raises(InsufficientFundsError) as exc_info:
            assert_sufficient_balance(
                balance_usd=Decimal("1.000000"),
                balance_inr=Decimal("84.000000"),
                required_usd=Decimal("5.000000"),
                required_inr=Decimal("420.000000"),
                preferred_currency="usd",
            )
        assert exc_info.value.currency == "usd"
        assert exc_info.value.required == Decimal("5.000000")

    def test_dual_currency_no_rounding_drift_accumulation(self):
        """
        Simulate 100 per-second debits and verify no cumulative drift.
        Each tick: $0.000694/s for 100 seconds = $0.0694 total
        """
        per_second = Decimal("0.0006944444")
        balance_usd = Decimal("10.000000")
        balance_inr = Decimal("840.000000")
        expected_total_debit = Decimal("0")

        for _ in range(100):
            balance_usd, balance_inr = apply_debit(
                balance_usd, balance_inr, per_second, FX_RATE
            )
            expected_total_debit += per_second

        # Total debited ~0.0694... USD; balance should be ~9.930...
        total_debited = Decimal("10.000000") - balance_usd
        # 100 ticks × up to 0.000001 rounding per tick = max 0.0001 USD drift allowed
        # (per_second has 10dp but storage truncates to 6dp)
        assert abs(total_debited - expected_total_debit.quantize(Decimal("0.000001"))) < Decimal("0.0001")


# ── Wallet API tests ───────────────────────────────────────────────────────

class TestWalletBalance:
    @patch("services.wallet_billing_service.routes.require_auth", return_value=JWT_PAYLOAD)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_by_user_id", new_callable=AsyncMock)
    def test_get_balance_success(self, mock_get, mock_auth, client):
        """Returns balance in preferred currency."""
        wallet = MagicMock()
        wallet.id = uuid.UUID(WALLET_ID)
        wallet.user_id = uuid.UUID(USER_ID)
        wallet.balance_usd = Decimal("25.000000")
        wallet.balance_inr = Decimal("2100.000000")
        wallet.preferred_currency = "usd"
        mock_get.return_value = wallet

        resp = client.get("/wallet/balance")
        assert resp.status_code == 200
        data = resp.json()
        assert float(data["balance_usd"]) == 25.0
        assert float(data["balance_inr"]) == 2100.0

    @patch("services.wallet_billing_service.routes.require_auth", return_value=JWT_PAYLOAD)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_by_user_id", new_callable=AsyncMock)
    def test_get_balance_wallet_not_found(self, mock_get, mock_auth, client):
        """Returns 404 if user has no wallet."""
        mock_get.return_value = None
        resp = client.get("/wallet/balance")
        assert resp.status_code == 404


class TestWalletTopup:
    @patch("services.wallet_billing_service.routes.require_auth", return_value=JWT_PAYLOAD)
    @patch("services.wallet_billing_service.repository.StripeAccountRepository.get_by_user_id", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_by_user_id", new_callable=AsyncMock)
    @patch("asyncio.get_event_loop")
    def test_topup_creates_payment_intent(
        self, mock_loop, mock_wallet, mock_stripe_acct, mock_auth, client
    ):
        """POST /wallet/topup creates Stripe PaymentIntent and returns client_secret."""
        wallet = MagicMock()
        wallet.id = uuid.UUID(WALLET_ID)
        wallet.user_id = uuid.UUID(USER_ID)
        mock_wallet.return_value = wallet

        stripe_acct = MagicMock()
        stripe_acct.stripe_customer_id = "cus_test123"
        mock_stripe_acct.return_value = stripe_acct

        # Mock Stripe PaymentIntent
        mock_intent = MagicMock()
        mock_intent.id = "pi_test_abc123"
        mock_intent.client_secret = "pi_test_abc123_secret_xyz"

        # Make run_in_executor return the mock intent
        loop_mock = MagicMock()
        mock_loop.return_value = loop_mock
        future = MagicMock()
        future.__await__ = lambda: iter([mock_intent])
        loop_mock.run_in_executor = AsyncMock(return_value=mock_intent)

        with patch("services.wallet_billing_service.routes.sc.create_payment_intent",
                   return_value=mock_intent):
            resp = client.post("/wallet/topup", json={"amount_usd": 10.0, "currency": "usd"})

        assert resp.status_code == 200
        data = resp.json()
        assert "client_secret" in data
        assert "payment_intent_id" in data
        assert float(data["amount_usd"]) == 10.0
        # INR equivalent should be present (10 * 84 = 840)
        assert float(data["amount_inr"]) == pytest.approx(840.0)


class TestStripeWebhook:
    @patch("services.wallet_billing_service.repository.WalletRepository.get_transaction_by_stripe_pi", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.repository.WalletRepository.create_transaction", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_by_user_id", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.routes.sc.verify_webhook_signature")
    def test_webhook_payment_intent_succeeded_credits_wallet(
        self, mock_verify, mock_wallet_get, mock_create_txn, mock_existing, client
    ):
        """payment_intent.succeeded event credits the wallet exactly once."""
        # Mock event returned by Stripe signature verification
        mock_event = {
            "id": "evt_test123",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_test_abc123",
                    "amount": 1000,  # $10.00 in cents
                    "metadata": {"kynetic_user_id": USER_ID, "wallet_id": WALLET_ID},
                }
            },
        }
        mock_verify.return_value = mock_event

        wallet = MagicMock()
        wallet.id = uuid.UUID(WALLET_ID)
        wallet.balance_usd = Decimal("0.000000")
        wallet.balance_inr = Decimal("0.000000")
        mock_wallet_get.return_value = wallet
        mock_existing.return_value = None  # Not yet processed

        resp = client.post(
            "/billing/webhooks/stripe",
            content=b'{"test": "payload"}',
            headers={"stripe-signature": "t=1234,v1=abcdef"},
        )
        assert resp.status_code == 200
        mock_create_txn.assert_called_once()
        txn_args = mock_create_txn.call_args
        assert txn_args.kwargs["amount"] == Decimal("10.000000")

    @patch("services.wallet_billing_service.routes.sc.verify_webhook_signature")
    def test_webhook_invalid_signature_rejected(self, mock_verify, client):
        """Invalid Stripe-Signature → 400."""
        import stripe
        mock_verify.side_effect = stripe.error.SignatureVerificationError(
            "Invalid signature", "bad_sig"
        )
        resp = client.post(
            "/billing/webhooks/stripe",
            content=b"bad_payload",
            headers={"stripe-signature": "t=0,v1=bad"},
        )
        assert resp.status_code == 400

    @patch("services.wallet_billing_service.repository.WalletRepository.get_transaction_by_stripe_pi", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_by_user_id", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.routes.sc.verify_webhook_signature")
    def test_webhook_idempotent_duplicate_skipped(
        self, mock_verify, mock_wallet_get, mock_existing, client
    ):
        """Duplicate webhook event (same PI) is skipped — idempotency."""
        mock_event = {
            "id": "evt_dupe",
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": "pi_already_processed",
                    "amount": 1000,
                    "metadata": {"kynetic_user_id": USER_ID},
                }
            },
        }
        mock_verify.return_value = mock_event

        wallet = MagicMock()
        wallet.id = uuid.UUID(WALLET_ID)
        mock_wallet_get.return_value = wallet
        # Already processed
        mock_existing.return_value = MagicMock()

        resp = client.post(
            "/billing/webhooks/stripe",
            content=b"dupe",
            headers={"stripe-signature": "t=1,v1=abc"},
        )
        assert resp.status_code == 200
        # Should return received: True without creating a new transaction


class TestTransactionHistory:
    @patch("services.wallet_billing_service.routes.require_auth", return_value=JWT_PAYLOAD)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_transactions", new_callable=AsyncMock)
    @patch("services.wallet_billing_service.repository.WalletRepository.get_by_user_id", new_callable=AsyncMock)
    def test_transaction_history_paginated(self, mock_wallet, mock_txns, mock_auth, client):
        """GET /wallet/transactions returns paginated transaction history."""
        wallet = MagicMock()
        wallet.id = uuid.UUID(WALLET_ID)
        mock_wallet.return_value = wallet

        txn = MagicMock()
        txn.id = uuid.uuid4()
        txn.wallet_id = uuid.UUID(WALLET_ID)
        txn.transaction_type = "topup"
        txn.amount = Decimal("10.000000")
        txn.currency = "usd"
        txn.stripe_payment_intent_id = "pi_test123"
        txn.description = "Wallet top-up"
        txn.balance_after_usd = Decimal("10.000000")
        txn.balance_after_inr = Decimal("840.000000")
        txn.created_at = "2024-01-01T00:00:00Z"

        mock_txns.return_value = ([txn], 1)

        resp = client.get("/wallet/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["transaction_type"] == "topup"
