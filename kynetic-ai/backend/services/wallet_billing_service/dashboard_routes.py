"""
Wallet & Billing Service — Dashboards & Financial Query Endpoints (dashboard_routes.py)

Endpoints (§11, §17):
- GET /v1/payouts: Host payout history with line-item traceability.
- GET /v1/ledger: Admin double-entry ledger browser.
- GET /v1/hosts/{id}/dashboard/financials: Host financial metrics (pending earnings, available balance, upcoming payout, effective commission rate).
"""

from decimal import Decimal
import uuid
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.payment_models_v7 import (
    HostEarnings,
    HostEarningsStatus,
    LedgerEntry,
    PaymentProviderAccount,
    Payout,
)
from services.wallet_billing_service.commission_service import CommissionResolver

router = APIRouter(prefix="/v1", tags=["financial_dashboards"])


@router.get("/payouts")
async def get_host_payouts(
    host_id: uuid.UUID = Query(...),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Host payout history with line-item traceability (§15, §17)."""
    stmt = select(Payout).where(Payout.host_id == host_id).order_by(Payout.created_at.desc())
    res = await session.execute(stmt)
    payouts = res.scalars().all()

    return {
        "host_id": str(host_id),
        "count": len(payouts),
        "payouts": [
            {
                "payout_id": str(p.id),
                "total_amount": float(p.total_amount),
                "currency": p.currency,
                "status": p.status.value,
                "provider_transfer_id": p.provider_transfer_id,
                "created_at": p.created_at.isoformat(),
            }
            for p in payouts
        ],
    }


@router.get("/ledger")
async def get_ledger_entries(
    account: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Admin-only double-entry ledger browser (§11, §16, §17)."""
    stmt = select(LedgerEntry)
    if account:
        stmt = stmt.where(LedgerEntry.account == account)
    stmt = stmt.order_by(LedgerEntry.created_at.desc()).limit(limit)

    res = await session.execute(stmt)
    entries = res.scalars().all()

    return {
        "count": len(entries),
        "entries": [
            {
                "id": str(e.id),
                "account": e.account,
                "entry_type": e.entry_type.value,
                "amount_usd": float(e.amount_usd),
                "description": e.description,
                "reference_id": e.reference_id,
                "created_at": e.created_at.isoformat(),
            }
            for e in entries
        ],
    }


@router.get("/hosts/{host_id}/dashboard/financials")
async def get_host_financial_dashboard(
    host_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Host dashboard financial summary (§17)."""
    # Sum pending earnings
    stmt_pending = select(func.sum(HostEarnings.net_amount)).where(
        HostEarnings.host_id == host_id,
        HostEarnings.status == HostEarningsStatus.pending_settlement,
    )
    res_p = await session.execute(stmt_pending)
    pending_sum = res_p.scalar() or 0.0

    # Sum settled earnings
    stmt_settled = select(func.sum(HostEarnings.net_amount)).where(
        HostEarnings.host_id == host_id,
        HostEarnings.status == HostEarningsStatus.settled,
    )
    res_s = await session.execute(stmt_settled)
    settled_sum = res_s.scalar() or 0.0

    # Fetch provider account
    acct_stmt = select(PaymentProviderAccount).where(PaymentProviderAccount.host_id == host_id)
    acct_res = await session.execute(acct_stmt)
    acct = acct_res.scalar_one_or_none()

    # Resolve effective commission rate
    comm_pct, _ = await CommissionResolver.resolve_commission_rate(session, host_id=host_id)

    return {
        "host_id": str(host_id),
        "pending_earnings_usd": float(pending_sum),
        "settled_earnings_usd": float(settled_sum),
        "effective_commission_pct": float(comm_pct),
        "provider_account_status": acct.account_status.value if acct else "not_configured",
        "provider": acct.provider if acct else "none",
        "linked_account_id": acct.linked_account_id if acct else None,
    }
