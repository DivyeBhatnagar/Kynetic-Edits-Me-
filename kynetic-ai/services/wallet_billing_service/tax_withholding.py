"""
Phase 16 — Tax Withholding Engine (Indian TDS Sec 194O & US 1099)

Implements statutory tax withholding rules:
  - India Sec 194O: 1% TDS on host payouts with verified PAN, 20% without PAN
  - US 1099-NEC: Track $600 USD threshold per calendar year
"""

from decimal import Decimal, ROUND_HALF_UP
import uuid
from pydantic import BaseModel


class TDSCalculationResult(BaseModel):
    user_id: str
    payout_id: str
    jurisdiction: str = "IN_TDS"
    gross_payout: Decimal
    tax_rate_pct: Decimal
    withheld_amount: Decimal
    net_payout: Decimal
    pan_or_tin: str | None


def calculate_indian_tds(
    user_id: str,
    payout_id: str,
    gross_payout_inr: Decimal,
    pan_number: str | None = None
) -> TDSCalculationResult:
    """
    Calculate Indian Section 194O TDS withholding.
    Rate = 1.00% if valid PAN provided, 20.00% if missing or invalid.
    """
    is_valid_pan = bool(pan_number and len(pan_number.strip()) == 10 and pan_number.isalnum())
    tax_rate_pct = Decimal("1.00") if is_valid_pan else Decimal("20.00")

    withheld_amount = (gross_payout_inr * (tax_rate_pct / Decimal("100"))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    net_payout = gross_payout_inr - withheld_amount

    return TDSCalculationResult(
        user_id=user_id,
        payout_id=payout_id,
        jurisdiction="IN_TDS",
        gross_payout=gross_payout_inr,
        tax_rate_pct=tax_rate_pct,
        withheld_amount=withheld_amount,
        net_payout=net_payout,
        pan_or_tin=pan_number if is_valid_pan else None,
    )


def check_us_1099_reporting_threshold(
    cumulative_payouts_usd: Decimal,
    threshold_usd: Decimal = Decimal("600.00")
) -> bool:
    """
    Returns True if US host cumulative calendar year payouts exceed 1099-NEC reporting threshold ($600).
    """
    return cumulative_payouts_usd >= threshold_usd
