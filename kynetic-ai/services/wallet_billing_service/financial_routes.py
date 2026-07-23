"""
Phase 16 — Financial Operations & Compliance FastAPI Router

API endpoints for double-entry posting, TDS tax calculation, dispute webhook processing,
and automated ledger reconciliation audits.
"""

from decimal import Decimal
import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from services.wallet_billing_service.ledger import (
    LedgerPosting,
    record_double_entry_transaction,
    UnbalancedLedgerError,
)
from services.wallet_billing_service.tax_withholding import (
    calculate_indian_tds,
    TDSCalculationResult,
)
from services.wallet_billing_service.chargeback_handler import (
    DisputeEventPayload,
    process_incoming_dispute,
    resolve_dispute,
)
from services.wallet_billing_service.reconciliation_job import (
    run_daily_ledger_reconciliation_audit,
    ReconciliationAuditReport,
)

router = APIRouter(prefix="/billing/financial", tags=["financial-operations"])


class PostTransactionRequest(BaseModel):
    transaction_id: str
    postings: list[LedgerPosting]


class TDSSubmitRequest(BaseModel):
    user_id: str
    payout_id: str
    gross_payout_inr: Decimal
    pan_number: Optional[str] = None


class AuditRunRequest(BaseModel):
    stripe_provider_balance: Decimal
    razorpay_provider_balance: Decimal
    internal_stripe_ledger: Decimal
    internal_razorpay_ledger: Decimal


@router.post("/ledger/post")
async def post_double_entry_ledger(payload: PostTransactionRequest):
    """Post double-entry ledger transaction enforcing sum(debit) == sum(credit)."""
    try:
        entries = record_double_entry_transaction(payload.transaction_id, payload.postings)
        return {"status": "success", "entries": entries}
    except UnbalancedLedgerError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/tax/calculate-tds", response_model=TDSCalculationResult)
async def compute_tds(payload: TDSSubmitRequest):
    """Calculate Indian Sec 194O TDS tax withholding for a host payout."""
    return calculate_indian_tds(
        user_id=payload.user_id,
        payout_id=payload.payout_id,
        gross_payout_inr=payload.gross_payout_inr,
        pan_number=payload.pan_number,
    )


@router.post("/disputes/webhook")
async def handle_dispute_webhook(payload: DisputeEventPayload):
    """Process Stripe/Razorpay dispute webhook event and freeze wallet funds."""
    res = process_incoming_dispute(payload)
    return {"status": "success", "result": res}


@router.post("/reconciliation/run", response_model=ReconciliationAuditReport)
async def run_reconciliation(payload: AuditRunRequest):
    """Run automated daily ledger reconciliation audit against provider balances."""
    return run_daily_ledger_reconciliation_audit(
        stripe_provider_balance=payload.stripe_provider_balance,
        razorpay_provider_balance=payload.razorpay_provider_balance,
        internal_stripe_ledger=payload.internal_stripe_ledger,
        internal_razorpay_ledger=payload.internal_razorpay_ledger,
    )
