"""
Billing & Payment Service — Signature-Verified & Replay-Protected Webhook Receiver (webhook_handler.py)

Security & Integrity:
1. HMAC Signature Verification before payload parsing.
2. DB-Level Replay Protection: WebhookEvent unique constraint on (provider, provider_event_id).
3. Direct Customer Payment recording in balanced double-entry financial ledger (§7).
"""

import json
import uuid
from decimal import Decimal
import structlog
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.payment_models_v7 import WebhookEvent, WebhookStatus
from services.wallet_billing_service.provider_interface import get_provider_for_host
from services.wallet_billing_service.ledger_service import LedgerService

log = structlog.get_logger(__name__)


async def process_incoming_webhook(
    provider: str,
    payload_bytes: bytes,
    signature: str,
    secret: str,
    session: AsyncSession,
) -> dict:
    adapter = get_provider_for_host("IN" if provider == "razorpay" else "US")

    # 1. HMAC Signature Verification
    valid_sig = await adapter.verify_webhook_signature(payload_bytes, signature, secret)
    if not valid_sig:
        log.warning("webhook.invalid_signature", provider=provider)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid HMAC signature")

    # Parse JSON
    try:
        data = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    event_id = data.get("event_id") or data.get("id") or str(uuid.uuid4())
    event_type = data.get("event", "payment.captured")

    # 2. Database-level Replay Protection
    evt = WebhookEvent(
        id=uuid.uuid4(),
        provider=provider,
        event_type=event_type,
        provider_event_id=event_id,
        payload=data,
        status=WebhookStatus.received,
    )
    session.add(evt)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        log.info("webhook.duplicate_ignored", provider=provider, event_id=event_id)
        return {"status": "duplicate_ignored", "event_id": event_id}

    # 3. Handle payment.captured -> Record Customer Payment in Double-Entry Ledger
    if event_type == "payment.captured":
        user_id_str = data.get("user_id") or data.get("payload", {}).get("user_id")
        amount = float(data.get("amount", 10.0))

        if user_id_str:
            u_id = uuid.UUID(user_id_str)
            dec_amount = Decimal(str(amount))

            await LedgerService.record_double_entry(
                session,
                entry_type="CUSTOMER_PAYMENT",
                account_debit="provider_clearing",
                account_credit=f"customer_account:{u_id}",
                amount_usd=dec_amount,
                reference_type="payment",
                reference_id=evt.id,
            )

            evt.status = WebhookStatus.processed
            await session.flush()

    return {"status": "received", "event_id": event_id}
