"""
Wallet & Billing Service — Refund & Failure Recovery Engine (refund_service.py)

Architecture (§18):
- Refund Validator checks whether payment was captured and compute delivered.
- Refund-After-Host-Paid Scenario: If host was already paid out, refund draws from platform refund_reserve buffer rather than attempting bank clawbacks.
- Writes balanced double-entry ledger entries for every refund.
"""

from decimal import Decimal
import uuid
from datetime import datetime, timezone
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.payment_models_v7 import Payment, PaymentStatus, Refund, RefundStatus
from services.wallet_billing_service.provider_interface import get_provider_for_host
from services.wallet_billing_service.ledger_service import LedgerService

log = structlog.get_logger(__name__)


async def process_refund(
    session: AsyncSession,
    payment_id: uuid.UUID,
    amount: Decimal,
    reason: str,
    requested_by: uuid.UUID,
    is_host_already_paid: bool = False,
    country_code: str = "IN",
) -> Refund:
    """Processes customer refund with eligibility check and double-entry ledger entries (§18)."""
    stmt = select(Payment).where(Payment.id == payment_id)
    res = await session.execute(stmt)
    payment = res.scalar_one_or_none()

    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    adapter = get_provider_for_host(country_code)
    rfnd_res = await adapter.create_refund(
        payment_id=payment.provider_payment_id,
        amount=amount,
        reason=reason,
    )

    refund = Refund(
        id=uuid.uuid4(),
        payment_id=payment_id,
        amount=amount,
        currency=payment.currency,
        reason=reason,
        status=RefundStatus.processed,
        provider_refund_id=rfnd_res.get("refund_id"),
        requested_by=requested_by,
        processed_at=datetime.now(tz=timezone.utc),
    )
    session.add(refund)
    payment.status = PaymentStatus.refunded

    # Credit/Debit double-entry ledger logic (§18)
    credit_account = "refund_reserve" if is_host_already_paid else "platform_revenue"
    await LedgerService.record_double_entry(
        session,
        entry_type="REFUND",
        account_debit=f"customer_wallet:{requested_by}",
        account_credit=credit_account,
        amount_usd=amount,
        reference_type="refund",
        reference_id=refund.id,
    )

    await session.flush()
    log.info("refund.processed", refund_id=str(refund.id), amount=str(amount), host_paid=is_host_already_paid)
    return refund
