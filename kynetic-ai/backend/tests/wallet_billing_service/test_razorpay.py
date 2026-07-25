"""
Tests — Phase 10: Razorpay client + billing service additions.

Tests:
  - RazorpayClient mock mode: create_order, verify_payment_signature, verify_webhook_signature, create_payout
  - GST invoice calculation: calculate_gst
  - Invoice number fiscal year logic: _get_fiscal_year
  - Billing config: razorpay settings present
"""

import pytest
from decimal import Decimal
from datetime import date

from services.wallet_billing_service.razorpay_client import RazorpayClient
from services.wallet_billing_service.invoice import calculate_gst, _get_fiscal_year


# ── Razorpay client — mock mode ────────────────────────────────────────────

class TestRazorpayClientMock:
    """All tests use mock=True — zero real API calls."""

    def setup_method(self):
        self.client = RazorpayClient(
            key_id="rzp_test_key",
            key_secret="test_secret",
            mock=True,
        )

    def test_create_order_returns_dict_with_required_fields(self):
        order = self.client.create_order(
            amount_inr=Decimal("500.00"),
            user_id="user-123",
            wallet_id="wallet-456",
        )
        assert "id" in order
        assert order["currency"] == "INR"
        assert order["status"] == "created"
        assert order["amount"] == 50000   # 500 INR in paise

    def test_create_order_id_starts_with_order(self):
        order = self.client.create_order(
            amount_inr=Decimal("100.00"),
            user_id="u",
            wallet_id="w",
        )
        assert order["id"].startswith("order_MOCK_")

    def test_create_order_paise_calculation(self):
        order = self.client.create_order(
            amount_inr=Decimal("1.50"),
            user_id="u",
            wallet_id="w",
        )
        assert order["amount"] == 150   # 1.50 INR = 150 paise

    def test_verify_payment_signature_mock_always_true(self):
        result = self.client.verify_payment_signature(
            razorpay_order_id="order_123",
            razorpay_payment_id="pay_456",
            razorpay_signature="fakesig",
        )
        assert result is True

    def test_verify_webhook_signature_mock_always_true(self):
        result = self.client.verify_webhook_signature(
            payload_body=b'{"event": "payment.captured"}',
            webhook_signature="fakesig",
        )
        assert result is True

    def test_create_payout_returns_mock_payout(self):
        payout = self.client.create_payout(
            account_number="1234567890",
            ifsc="HDFC0001234",
            beneficiary_name="Test Host",
            amount_inr=Decimal("1000.00"),
        )
        assert "id" in payout
        assert payout["id"].startswith("pout_MOCK_")
        assert payout["currency"] == "INR"
        assert payout["amount"] == 100000   # 1000 INR in paise
        assert payout["status"] == "queued"

    def test_create_payout_custom_reference(self):
        payout = self.client.create_payout(
            account_number="111",
            ifsc="SBIN0000001",
            beneficiary_name="Host",
            amount_inr=Decimal("250.00"),
            reference_id="custom-ref-001",
        )
        assert payout["reference_id"] == "custom-ref-001"


# ── GST calculation ────────────────────────────────────────────────────────

class TestGSTCalculation:
    """Tests for calculate_gst() — 18% inclusive GST."""

    def test_gst_calculation_basic(self):
        """₹118 inclusive → ₹100 base + ₹18 GST."""
        base, gst = calculate_gst(Decimal("118.00"))
        assert base == Decimal("100.00")
        assert gst == Decimal("18.00")

    def test_gst_components_sum_to_total(self):
        """Base + GST must equal input (no rounding loss)."""
        for amount in ["500.00", "1180.00", "99.50", "1000.00"]:
            base, gst = calculate_gst(Decimal(amount))
            # Allow 1 paise rounding tolerance
            diff = abs((base + gst) - Decimal(amount))
            assert diff <= Decimal("0.01"), f"Rounding error for {amount}: base={base} gst={gst}"

    def test_gst_is_18_percent_of_base(self):
        """GST should be ~18% of the base amount."""
        base, gst = calculate_gst(Decimal("1000.00"))
        # 1000 / 1.18 ≈ 847.46 base, 152.54 GST
        ratio = gst / base
        assert abs(ratio - Decimal("0.18")) < Decimal("0.001")

    def test_gst_small_amount(self):
        """Minimal amount — no zero-division or overflow."""
        base, gst = calculate_gst(Decimal("1.00"))
        assert base > 0
        assert gst > 0

    def test_gst_returns_two_decimals(self):
        """Both outputs are rounded to 2 decimal places."""
        base, gst = calculate_gst(Decimal("199.99"))
        assert base == base.quantize(Decimal("0.01"))
        assert gst == gst.quantize(Decimal("0.01"))


# ── Fiscal year logic ──────────────────────────────────────────────────────

class TestFiscalYear:
    """Tests for _get_fiscal_year() — Indian fiscal year Apr–Mar."""

    def test_april_start_of_fiscal_year(self):
        assert _get_fiscal_year(date(2024, 4, 1)) == "2024-25"

    def test_march_end_of_fiscal_year(self):
        assert _get_fiscal_year(date(2025, 3, 31)) == "2024-25"

    def test_january_mid_fiscal_year(self):
        assert _get_fiscal_year(date(2025, 1, 15)) == "2024-25"

    def test_new_fiscal_year_april(self):
        assert _get_fiscal_year(date(2025, 4, 1)) == "2025-26"

    def test_format_two_digit_year(self):
        fy = _get_fiscal_year(date(2024, 6, 15))
        # Should be "2024-25" not "2024-2025"
        parts = fy.split("-")
        assert len(parts) == 2
        assert len(parts[1]) == 2

    def test_year_2000(self):
        """Check century boundary."""
        fy = _get_fiscal_year(date(2000, 4, 15))
        assert fy == "2000-01"


# ── Invoice number format ──────────────────────────────────────────────────

class TestInvoiceNumberFormat:
    def test_format_pattern(self):
        """Confirm KYN/{fy}/{seq:06d} format."""
        from services.wallet_billing_service.invoice import INVOICE_PREFIX, _get_fiscal_year
        fy = _get_fiscal_year(date(2024, 6, 1))
        expected = f"KYN/{fy}/000001"
        # Just test the format, not DB interaction
        formatted = f"{INVOICE_PREFIX}/{fy}/{1:06d}"
        assert formatted == expected

    def test_prefix_is_kyn(self):
        from services.wallet_billing_service.invoice import INVOICE_PREFIX
        assert INVOICE_PREFIX == "KYN"

    def test_six_digit_zero_padding(self):
        from services.wallet_billing_service.invoice import INVOICE_PREFIX, _get_fiscal_year
        fy = _get_fiscal_year()
        assert f"{INVOICE_PREFIX}/{fy}/{999999:06d}" == f"KYN/{fy}/999999"
        assert f"{INVOICE_PREFIX}/{fy}/{1:06d}" == f"KYN/{fy}/000001"
