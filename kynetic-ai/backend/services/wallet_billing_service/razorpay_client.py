"""
Razorpay client wrapper — Phase 10.

Wraps the Razorpay Python SDK for:
  - Creating UPI/Card/Netbanking payment orders (wallet top-up)
  - Verifying Razorpay webhook signatures (HMAC-SHA256)
  - Creating Fund Account + Payout for host INR payouts

MOCK_MODE (default: true in dev/CI):
  When RAZORPAY_MOCK_MODE=true, all methods return deterministic mock
  responses — no real Razorpay API calls are made.

Real mode requires:
  RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET env vars.
"""

from __future__ import annotations

import hashlib
import hmac
import uuid
from decimal import Decimal
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class RazorpayMockOrder:
    """Deterministic mock order returned in MOCK_MODE."""
    def __init__(self, amount_inr: Decimal) -> None:
        self.id = f"order_MOCK_{uuid.uuid4().hex[:12].upper()}"
        self.amount = int(amount_inr * 100)   # paise
        self.currency = "INR"
        self.status = "created"
        self.receipt = f"rcpt_{uuid.uuid4().hex[:8]}"

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


class RazorpayClient:
    """
    Thin wrapper around razorpay.Client with mock-mode support.

    Usage:
        client = RazorpayClient(key_id="rzp_test_xxx", key_secret="secret", mock=True)
        order = client.create_order(amount_inr=Decimal("500"))
        client.verify_signature(order_id, payment_id, signature)
    """

    def __init__(self, key_id: str, key_secret: str, mock: bool = True) -> None:
        self._mock = mock
        self._key_id = key_id
        self._key_secret = key_secret
        self._client: Any = None

        if not mock:
            try:
                import razorpay  # type: ignore[import]
                self._client = razorpay.Client(auth=(key_id, key_secret))
            except ImportError as e:
                raise RuntimeError(
                    "razorpay package not installed. "
                    "Add it to requirements or set RAZORPAY_MOCK_MODE=true."
                ) from e

    # ── Order creation (wallet top-up) ─────────────────────────────────────

    def create_order(
        self,
        amount_inr: Decimal,
        user_id: str,
        wallet_id: str,
        receipt: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a Razorpay order for a wallet top-up.

        Returns a dict with at minimum: id, amount (paise), currency, status.
        Frontend uses `order.id` to initialise Razorpay Checkout.
        """
        amount_paise = int(amount_inr * 100)   # Razorpay uses paise (1/100 INR)
        _receipt = receipt or f"kyn_{uuid.uuid4().hex[:10]}"

        if self._mock:
            order = RazorpayMockOrder(amount_inr)
            logger.info(
                "razorpay_create_order_mock",
                order_id=order.id,
                amount_paise=amount_paise,
                user_id=user_id,
            )
            return {
                "id": order.id,
                "amount": amount_paise,
                "currency": "INR",
                "status": "created",
                "receipt": _receipt,
            }

        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": _receipt,
            "notes": {"kynetic_user_id": user_id, "wallet_id": wallet_id},
        }
        order = self._client.order.create(data=payload)
        logger.info(
            "razorpay_create_order",
            order_id=order["id"],
            amount_paise=amount_paise,
            user_id=user_id,
        )
        return dict(order)

    # ── Signature verification ──────────────────────────────────────────────

    def verify_payment_signature(
        self,
        razorpay_order_id: str,
        razorpay_payment_id: str,
        razorpay_signature: str,
    ) -> bool:
        """
        Verify Razorpay payment signature (HMAC-SHA256).

        Returns True if signature is valid, False otherwise.
        In mock mode, always returns True.
        """
        if self._mock:
            return True

        try:
            self._client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            })
            return True
        except Exception:
            return False

    def verify_webhook_signature(
        self, payload_body: bytes, webhook_signature: str
    ) -> bool:
        """
        Verify Razorpay webhook signature.

        Razorpay uses HMAC-SHA256 of raw body with webhook_secret.
        In mock mode, always returns True.
        """
        if self._mock:
            return True

        expected = hmac.new(
            self._key_secret.encode(), payload_body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, webhook_signature)

    # ── Host payout ─────────────────────────────────────────────────────────

    def create_payout(
        self,
        account_number: str,
        ifsc: str,
        beneficiary_name: str,
        amount_inr: Decimal,
        purpose: str = "payout",
        reference_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Initiate a fund payout to a host's bank account.

        In mock mode returns a deterministic mock payout record.
        """
        amount_paise = int(amount_inr * 100)
        _ref = reference_id or uuid.uuid4().hex

        if self._mock:
            mock_id = f"pout_MOCK_{uuid.uuid4().hex[:12].upper()}"
            logger.info(
                "razorpay_payout_mock",
                payout_id=mock_id,
                amount_paise=amount_paise,
                purpose=purpose,
            )
            return {
                "id": mock_id,
                "amount": amount_paise,
                "currency": "INR",
                "status": "queued",
                "reference_id": _ref,
            }

        # Real: create fund_account + initiate payout
        # (Fund Account creation is idempotent by account_number+ifsc in prod)
        fund_account = self._client.fund_account.create({
            "contact_id": "NOT_SET",  # Should be set from host profile in production
            "account_type": "bank_account",
            "bank_account": {
                "name": beneficiary_name,
                "ifsc": ifsc,
                "account_number": account_number,
            },
        })
        payout = self._client.payout.create({
            "account_number": account_number,  # Razorpay X business account
            "fund_account_id": fund_account["id"],
            "amount": amount_paise,
            "currency": "INR",
            "mode": "IMPS",
            "purpose": purpose,
            "reference_id": _ref,
            "queue_if_low_balance": True,
        })
        return dict(payout)
