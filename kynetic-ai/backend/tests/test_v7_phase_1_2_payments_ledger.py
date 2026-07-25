"""
Implementation Plan v7 Phase 1 & Phase 2 Integration Tests — Payment Collection & Ledger Foundation

Tests:
1. Razorpay Adapter & Signature Verification: create_order & verify_webhook_signature (HMAC-SHA256)
2. Database-Level Webhook Replay Protection: WebhookEvent unique constraint on (provider, provider_event_id)
3. Balanced Double-Entry Financial Ledger: LedgerService.record_double_entry & reconcile_ledger
"""

import hmac
import hashlib
import json
import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import User, UserRole
from services.wallet_billing_service.provider_interface import RazorpayRouteAdapter, StripeConnectAdapter, get_provider_for_host
from services.wallet_billing_service.webhook_handler import process_incoming_webhook
from services.wallet_billing_service.ledger_service import LedgerService


@pytest.mark.asyncio
async def test_razorpay_adapter_order_and_signature():
    adapter = RazorpayRouteAdapter()
    order = await adapter.create_order(Decimal("50.00"), "USD", {"user_id": "u123"})
    assert order["provider"] == "razorpay"
    assert order["status"] == "created"

    secret = "secret_key_123"
    payload = b'{"event":"payment.captured","amount":50.0}'
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # Valid signature
    is_valid = await adapter.verify_webhook_signature(payload, sig, secret)
    assert is_valid is True

    # Tampered signature
    is_valid_tampered = await adapter.verify_webhook_signature(payload, "invalid_sig", secret)
    assert is_valid_tampered is False


@pytest.mark.asyncio
async def test_webhook_replay_protection(db_session: AsyncSession):
    dev_id = uuid.uuid4()
    dev = User(id=dev_id, email="wh@example.com", hashed_password="hash", role=UserRole.DEVELOPER)
    db_session.add(dev)
    await db_session.commit()

    secret = "rzp_secret_456"
    event_id = f"evt_rzp_{uuid.uuid4().hex[:8]}"
    payload_dict = {
        "id": event_id,
        "event": "payment.captured",
        "user_id": str(dev_id),
        "amount": 25.0,
    }
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()

    # First delivery -> processed
    res1 = await process_incoming_webhook("razorpay", payload_bytes, signature, secret, db_session)
    assert res1["status"] == "received"

    # Second delivery (replay attack / duplicate webhook) -> duplicate_ignored
    res2 = await process_incoming_webhook("razorpay", payload_bytes, signature, secret, db_session)
    assert res2["status"] == "duplicate_ignored"


@pytest.mark.asyncio
async def test_double_entry_ledger_balancing_and_reconciliation(db_session: AsyncSession):
    u_id = uuid.uuid4()
    h_id = uuid.uuid4()
    ref_id = uuid.uuid4()

    # 1. Customer topup ($100)
    entries1 = await LedgerService.record_double_entry(
        db_session, "CUSTOMER_PAYMENT", "provider_clearing", f"customer_wallet:{u_id}", Decimal("100.00"), "order", ref_id
    )
    assert len(entries1) == 2

    # 2. Compute usage debit ($50) & Commission split ($10 platform, $40 host)
    entries2 = await LedgerService.record_double_entry(
        db_session, "USAGE_DEBIT", f"customer_wallet:{u_id}", "platform_revenue", Decimal("50.00"), "session", ref_id
    )
    entries3 = await LedgerService.record_double_entry(
        db_session, "COMMISSION_SPLIT", "platform_revenue", f"host_payable:{h_id}", Decimal("40.00"), "session", ref_id
    )
    assert len(entries2) == 2
    assert len(entries3) == 2

    # 3. Daily Reconciliation Check
    reconciliation = await LedgerService.reconcile_ledger(db_session)
    assert reconciliation["reconciled"] is True
    assert reconciliation["discrepancy_usd"] == 0.0
