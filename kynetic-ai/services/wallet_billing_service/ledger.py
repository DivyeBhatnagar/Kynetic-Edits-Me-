"""
Phase 16 — Double-Entry Accounting Ledger Engine

Enforces audit-proof double-entry accounting rules:
  Every transaction MUST generate balanced debit and credit entries where:
    sum(debit) == sum(credit)
"""

from decimal import Decimal, ROUND_HALF_UP
import uuid
from pydantic import BaseModel, Field


class UnbalancedLedgerError(Exception):
    pass


class LedgerPosting(BaseModel):
    account: str
    debit: Decimal = Decimal("0.0000")
    credit: Decimal = Decimal("0.0000")
    currency: str = "USD"


def record_double_entry_transaction(
    transaction_id: str,
    postings: list[LedgerPosting]
) -> list[dict]:
    """
    Validate and post a set of double-entry ledger postings for a transaction.
    Raises UnbalancedLedgerError if sum(debit) != sum(credit).
    """
    if not postings or len(postings) < 2:
        raise UnbalancedLedgerError("A double-entry transaction requires at least 2 postings")

    total_debit = sum(p.debit for p in postings).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    total_credit = sum(p.credit for p in postings).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    if total_debit != total_credit:
        raise UnbalancedLedgerError(
            f"Unbalanced double-entry transaction {transaction_id}: "
            f"Total Debit ({total_debit}) != Total Credit ({total_credit})"
        )

    recorded_entries = []
    for p in postings:
        entry = {
            "id": str(uuid.uuid4()),
            "transaction_id": transaction_id,
            "account": p.account,
            "debit": p.debit,
            "credit": p.credit,
            "currency": p.currency,
        }
        recorded_entries.append(entry)

    return recorded_entries


def build_topup_postings(
    amount: Decimal,
    provider: str = "stripe",
    currency: str = "USD"
) -> list[LedgerPosting]:
    """
    Developer Wallet Topup:
      Debit: assets:stripe (or assets:razorpay)
      Credit: liabilities:user_wallet
    """
    asset_account = f"assets:{provider.lower()}"
    return [
        LedgerPosting(account=asset_account, debit=amount, credit=Decimal("0.0000"), currency=currency),
        LedgerPosting(account="liabilities:user_wallet", debit=Decimal("0.0000"), credit=amount, currency=currency),
    ]


def build_rental_payout_postings(
    total_cost: Decimal,
    host_share_pct: Decimal = Decimal("0.85"),
    currency: str = "USD"
) -> list[LedgerPosting]:
    """
    Compute Rental Settlement:
      Debit: liabilities:user_wallet (Total Cost)
      Credit: expenses:host_payout (85% Host Share)
      Credit: revenue:platform_fee (15% Platform Commission)
    """
    host_payout = (total_cost * host_share_pct).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    platform_fee = total_cost - host_payout

    return [
        LedgerPosting(account="liabilities:user_wallet", debit=total_cost, credit=Decimal("0.0000"), currency=currency),
        LedgerPosting(account="expenses:host_payout", debit=Decimal("0.0000"), credit=host_payout, currency=currency),
        LedgerPosting(account="revenue:platform_fee", debit=Decimal("0.0000"), credit=platform_fee, currency=currency),
    ]
