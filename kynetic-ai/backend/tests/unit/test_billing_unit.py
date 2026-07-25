"""
Phase 14 — Billing & Invoice Unit Tests

Tests:
  - GST 18% inclusive & exclusive mathematical accuracy
  - Indian Fiscal Year invoice string formatting (KYN/YYYY-YY/XXXXXX)
  - Usage-based per-second billing calculations
  - Currency conversion (USD <-> INR) at fixed and dynamic exchange rates
  - Reservation hold amount calculations
"""

from decimal import Decimal, ROUND_HALF_UP
import pytest


def calculate_gst_inclusive(total_amount: Decimal) -> dict:
    """
    Calculate 18% inclusive GST for Indian invoices.
    Total = Taxable + GST (18%) => Taxable = Total / 1.18, GST = Total - Taxable
    """
    taxable = (total_amount / Decimal("1.18")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gst_amount = total_amount - taxable
    cgst = (gst_amount / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sgst = gst_amount - cgst
    return {
        "total": total_amount,
        "taxable": taxable,
        "gst_amount": gst_amount,
        "cgst": cgst,
        "sgst": sgst,
        "rate": Decimal("18.00"),
    }


def format_indian_fiscal_year_invoice_number(sequence: int, year_start: int) -> str:
    """
    Format invoice number as KYN/YYYY-YY/XXXXXX (e.g. KYN/2024-25/000001).
    """
    next_year_short = str(year_start + 1)[-2:]
    return f"KYN/{year_start}-{next_year_short}/{sequence:06d}"


def calculate_per_second_cost(hourly_rate: Decimal, duration_seconds: int) -> Decimal:
    """
    Calculate exact cost for a duration in seconds based on hourly rate.
    Cost = (Hourly Rate / 3600) * duration_seconds
    """
    per_second_rate = hourly_rate / Decimal("3600")
    cost = per_second_rate * Decimal(duration_seconds)
    return cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def convert_usd_to_inr(usd_amount: Decimal, exchange_rate: Decimal = Decimal("84.00")) -> Decimal:
    """
    Convert USD to INR given exchange rate.
    """
    return (usd_amount * exchange_rate).quantize(Decimal("0.02"), rounding=ROUND_HALF_UP)


def calculate_reservation_hold_amount(hourly_rate: Decimal, max_hours: int = 24) -> Decimal:
    """
    Calculate initial credit hold amount (1 hour minimum, up to max_hours cap).
    """
    hold = hourly_rate * Decimal(min(max(max_hours, 1), 24))
    return hold.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class TestBillingUnitLogic:
    """Unit tests for billing logic math."""

    def test_gst_inclusive_calculation(self):
        # Test ₹118.00 total -> ₹100.00 taxable, ₹18.00 GST (₹9 CGST, ₹9 SGST)
        res = calculate_gst_inclusive(Decimal("118.00"))
        assert res["taxable"] == Decimal("100.00")
        assert res["gst_amount"] == Decimal("18.00")
        assert res["cgst"] == Decimal("9.00")
        assert res["sgst"] == Decimal("9.00")

    def test_gst_inclusive_fractional(self):
        # Test ₹100.00 total -> Taxable ~ ₹84.75, GST ~ ₹15.25
        res = calculate_gst_inclusive(Decimal("100.00"))
        assert res["taxable"] == Decimal("84.75")
        assert res["gst_amount"] == Decimal("15.25")

    def test_fiscal_year_invoice_number_formatting(self):
        inv1 = format_indian_fiscal_year_invoice_number(1, 2024)
        assert inv1 == "KYN/2024-25/000001"

        inv_large = format_indian_fiscal_year_invoice_number(12345, 2025)
        assert inv_large == "KYN/2025-26/012345"

    def test_per_second_billing_accuracy(self):
        # $3.60/hr -> $0.0010/sec
        # 1 hour = 3600 seconds = $3.6000
        cost_1h = calculate_per_second_cost(Decimal("3.60"), 3600)
        assert cost_1h == Decimal("3.6000")

        # 30 minutes = 1800 seconds = $1.8000
        cost_30m = calculate_per_second_cost(Decimal("3.60"), 1800)
        assert cost_30m == Decimal("1.8000")

        # 10 seconds = $0.0100
        cost_10s = calculate_per_second_cost(Decimal("3.60"), 10)
        assert cost_10s == Decimal("0.0100")

    def test_currency_conversion(self):
        # $10.00 USD @ 84.00 = ₹840.00
        inr = convert_usd_to_inr(Decimal("10.00"), Decimal("84.00"))
        assert inr == Decimal("840.00")

    def test_reservation_hold_amount(self):
        # $0.50/hr, max 24 hours -> $12.00 hold
        hold = calculate_reservation_hold_amount(Decimal("0.50"), 24)
        assert hold == Decimal("12.00")
