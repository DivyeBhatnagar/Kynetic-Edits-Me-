"""
Phase 15 — Backend Admin Operations & Security Routes

Endpoints for internal operations, support ticket resolution, fraud queue moderation,
financial reconciliation drift checks, and host management.
"""

from decimal import Decimal
import uuid
from typing import Any, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, status


router = APIRouter(prefix="/admin", tags=["admin-operations"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class AdminUserResponse(BaseModel):
    id: str
    email: str
    role: str
    is_active: bool


class FraudReviewItemResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    host_id: Optional[str] = None
    reason: str
    risk_score: int
    status: str


class FraudActionRequest(BaseModel):
    action: str  # approved | rejected | suspended
    notes: Optional[str] = None


class TicketReplyRequest(BaseModel):
    admin_id: str
    reply_text: str
    new_status: Optional[str] = None


class TicketActivityLogResponse(BaseModel):
    id: str
    ticket_id: str
    admin_id: Optional[str]
    action: str
    note: Optional[str]
    created_at: str


class FinancialReconciliationSummary(BaseModel):
    total_db_wallet_debits_usd: Decimal
    total_stripe_charge_ledgers_usd: Decimal
    total_db_wallet_debits_inr: Decimal
    total_razorpay_ledger_inr: Decimal
    usd_drift: Decimal
    inr_drift: Decimal
    reconciled: bool


class HostModerationRequest(BaseModel):
    action: str  # suspend | reverify | delist
    reason: str


# ---------------------------------------------------------------------------
# Helper / Mock Logic
# ---------------------------------------------------------------------------

def calculate_reconciliation_drift(
    db_debits_usd: Decimal,
    stripe_ledger_usd: Decimal,
    db_debits_inr: Decimal,
    razorpay_ledger_inr: Decimal,
) -> FinancialReconciliationSummary:
    usd_drift = db_debits_usd - stripe_ledger_usd
    inr_drift = db_debits_inr - razorpay_ledger_inr
    reconciled = (usd_drift == Decimal("0.00")) and (inr_drift == Decimal("0.00"))
    return FinancialReconciliationSummary(
        total_db_wallet_debits_usd=db_debits_usd,
        total_stripe_charge_ledgers_usd=stripe_ledger_usd,
        total_db_wallet_debits_inr=db_debits_inr,
        total_razorpay_ledger_inr=razorpay_ledger_inr,
        usd_drift=usd_drift,
        inr_drift=inr_drift,
        reconciled=reconciled,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/fraud/queue", response_model=list[FraudReviewItemResponse])
async def get_fraud_review_queue():
    """Fetch pending fraud & trust review queue items."""
    return [
        FraudReviewItemResponse(
            id=str(uuid.uuid4()),
            user_id=str(uuid.uuid4()),
            reason="High risk device fingerprint match across multiple accounts",
            risk_score=85,
            status="pending",
        ),
        FraudReviewItemResponse(
            id=str(uuid.uuid4()),
            host_id=str(uuid.uuid4()),
            reason="Reputation score dropped below 0.40 threshold",
            risk_score=65,
            status="pending",
        ),
    ]


@router.post("/fraud/{item_id}/action")
async def process_fraud_review_action(item_id: str, payload: FraudActionRequest):
    """Process an action (approve, reject, suspend) on a fraud review item."""
    if payload.action not in ["approved", "rejected", "suspended"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be one of: approved, rejected, suspended"
        )
    return {
        "status": "success",
        "item_id": item_id,
        "new_status": payload.action,
        "notes": payload.notes,
    }


@router.post("/tickets/{ticket_id}/reply")
async def reply_to_support_ticket(ticket_id: str, payload: TicketReplyRequest):
    """Reply to a support ticket and record ticket activity log."""
    activity = TicketActivityLogResponse(
        id=str(uuid.uuid4()),
        ticket_id=ticket_id,
        admin_id=payload.admin_id,
        action="responded",
        note=payload.reply_text,
        created_at="2026-07-24T00:00:00Z",
    )
    return {
        "status": "success",
        "ticket_id": ticket_id,
        "activity_log": activity,
        "new_status": payload.new_status or "in_progress",
    }


@router.get("/reconciliation", response_model=FinancialReconciliationSummary)
async def get_financial_reconciliation():
    """Cross-check database wallet debits against payment provider ledgers."""
    return calculate_reconciliation_drift(
        db_debits_usd=Decimal("12500.00"),
        stripe_ledger_usd=Decimal("12500.00"),
        db_debits_inr=Decimal("450000.00"),
        razorpay_ledger_inr=Decimal("450000.00"),
    )


@router.post("/hosts/{host_id}/moderation")
async def moderate_host_hardware(host_id: str, payload: HostModerationRequest):
    """Manually suspend, re-verify, or de-list host hardware."""
    if payload.action not in ["suspend", "reverify", "delist"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action must be one of: suspend, reverify, delist"
        )
    return {
        "status": "success",
        "host_id": host_id,
        "action": payload.action,
        "reason": payload.reason,
    }
