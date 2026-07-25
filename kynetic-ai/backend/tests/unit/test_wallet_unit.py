"""
Phase 14 — Wallet Ledger & Transaction Unit Tests

Tests:
  - Wallet balance credit & debit rules
  - Overdraft protection (insufficient balance errors)
  - Razorpay paise <-> INR unit conversions
  - Transaction type validations
"""

from decimal import Decimal
import pytest


class InsufficientBalanceError(Exception):
    pass


class WalletAccount:
    """Pure unit model simulating wallet ledger balance behavior."""

    def __init__(self, initial_balance_usd: Decimal = Decimal("0.00"), initial_balance_inr: Decimal = Decimal("0.00")):
        self.balance_usd = initial_balance_usd
        self.balance_inr = initial_balance_inr

    def topup(self, amount: Decimal, currency: str = "USD") -> Decimal:
        if amount <= Decimal("0.00"):
            raise ValueError("Topup amount must be positive")
        if currency.upper() == "USD":
            self.balance_usd += amount
            return self.balance_usd
        elif currency.upper() == "INR":
            self.balance_inr += amount
            return self.balance_inr
        else:
            raise ValueError(f"Unsupported currency: {currency}")

    def debit(self, amount: Decimal, currency: str = "USD") -> Decimal:
        if amount <= Decimal("0.00"):
            raise ValueError("Debit amount must be positive")

        if currency.upper() == "USD":
            if self.balance_usd < amount:
                raise InsufficientBalanceError(
                    f"Insufficient USD balance: {self.balance_usd} < {amount}"
                )
            self.balance_usd -= amount
            return self.balance_usd
        elif currency.upper() == "INR":
            if self.balance_inr < amount:
                raise InsufficientBalanceError(
                    f"Insufficient INR balance: {self.balance_inr} < {amount}"
                )
            self.balance_inr -= amount
            return self.balance_inr
        else:
            raise ValueError(f"Unsupported currency: {currency}")


def inr_to_razorpay_paise(amount_inr: Decimal) -> int:
    """Convert ₹100.50 INR to 10050 paise integer."""
    return int((amount_inr * Decimal("100")).quantize(Decimal("1")))


def razorpay_paise_to_inr(paise: int) -> Decimal:
    """Convert 10050 paise integer to ₹100.50 INR Decimal."""
    return (Decimal(paise) / Decimal("100")).quantize(Decimal("0.01"))


class TestWalletUnitLogic:
    """Unit tests for wallet transactions."""

    def test_wallet_topup_usd(self):
        wallet = WalletAccount(Decimal("10.00"))
        new_bal = wallet.topup(Decimal("25.00"), "USD")
        assert new_bal == Decimal("35.00")
        assert wallet.balance_usd == Decimal("35.00")

    def test_wallet_topup_inr(self):
        wallet = WalletAccount(initial_balance_inr=Decimal("500.00"))
        new_bal = wallet.topup(Decimal("1000.00"), "INR")
        assert new_bal == Decimal("1500.00")

    def test_wallet_debit_success(self):
        wallet = WalletAccount(Decimal("50.00"))
        rem_bal = wallet.debit(Decimal("15.50"), "USD")
        assert rem_bal == Decimal("34.50")

    def test_wallet_debit_overdraft_prevention(self):
        wallet = WalletAccount(Decimal("10.00"))
        with pytest.raises(InsufficientBalanceError):
            wallet.debit(Decimal("20.00"), "USD")

    def test_invalid_negative_topup_or_debit(self):
        wallet = WalletAccount(Decimal("10.00"))
        with pytest.raises(ValueError):
            wallet.topup(Decimal("-5.00"), "USD")
        with pytest.raises(ValueError):
            wallet.debit(Decimal("-5.00"), "USD")

    def test_razorpay_paise_conversion(self):
        paise = inr_to_razorpay_paise(Decimal("100.50"))
        assert paise == 10050

        inr = razorpay_paise_to_inr(10050)
        assert inr == Decimal("100.50")
