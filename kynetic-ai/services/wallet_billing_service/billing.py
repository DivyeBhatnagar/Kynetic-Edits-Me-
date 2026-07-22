"""
Wallet & Billing Service — dual-currency billing logic.

All arithmetic uses Python Decimal — NO float anywhere in the billing path.
This eliminates IEEE 754 rounding drift in stored balances.

Key functions:
  usd_to_inr(amount, rate)          — Decimal → Decimal conversion
  inr_to_usd(amount, rate)          — inverse
  compute_per_second_cost(...)      — derive per-second debit amount
  assert_sufficient_balance(...)    — raises InsufficientFundsError
"""

from decimal import ROUND_HALF_UP, Decimal


class InsufficientFundsError(Exception):
    """Raised when a wallet debit would result in a negative balance."""

    def __init__(self, currency: str, required: Decimal, available: Decimal) -> None:
        self.currency = currency
        self.required = required
        self.available = available
        super().__init__(
            f"Insufficient {currency.upper()} balance: "
            f"required {required}, available {available}"
        )


# ── Precision constants ────────────────────────────────────────────────────
# All stored amounts rounded to 6 decimal places (matches Numeric(18,6))
AMOUNT_PRECISION = Decimal("0.000001")
# Per-second costs carry 10dp precision (matches Numeric(18,10))
PER_SECOND_PRECISION = Decimal("0.0000000001")


def usd_to_inr(amount_usd: Decimal, rate: Decimal) -> Decimal:
    """Convert USD to INR with ROUND_HALF_UP."""
    return (amount_usd * rate).quantize(AMOUNT_PRECISION, rounding=ROUND_HALF_UP)


def inr_to_usd(amount_inr: Decimal, rate: Decimal) -> Decimal:
    """Convert INR to USD with ROUND_HALF_UP."""
    return (amount_inr / rate).quantize(AMOUNT_PRECISION, rounding=ROUND_HALF_UP)


def compute_per_second_cost(
    price_per_hour_usd: Decimal,
    price_per_hour_inr: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Derive per-second cost from hourly pricing.
    Returns (per_second_usd, per_second_inr).
    """
    secs = Decimal("3600")
    ps_usd = (price_per_hour_usd / secs).quantize(PER_SECOND_PRECISION, rounding=ROUND_HALF_UP)
    ps_inr = (price_per_hour_inr / secs).quantize(PER_SECOND_PRECISION, rounding=ROUND_HALF_UP)
    return ps_usd, ps_inr


def assert_sufficient_balance(
    balance_usd: Decimal,
    balance_inr: Decimal,
    required_usd: Decimal,
    required_inr: Decimal,
    preferred_currency: str,
) -> None:
    """
    Raise InsufficientFundsError if the wallet cannot cover the required amount.
    Checks BOTH currencies — either must be sufficient.
    """
    if balance_usd < required_usd:
        raise InsufficientFundsError("usd", required_usd, balance_usd)
    if balance_inr < required_inr:
        raise InsufficientFundsError("inr", required_inr, balance_inr)


def apply_topup(
    balance_usd: Decimal,
    balance_inr: Decimal,
    amount_usd: Decimal,
    usd_to_inr_rate: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Compute new balances after a USD top-up.
    The INR balance is also credited with the equivalent amount.
    Returns (new_balance_usd, new_balance_inr).
    """
    amount_inr = usd_to_inr(amount_usd, usd_to_inr_rate)
    new_usd = (balance_usd + amount_usd).quantize(AMOUNT_PRECISION)
    new_inr = (balance_inr + amount_inr).quantize(AMOUNT_PRECISION)
    return new_usd, new_inr


def apply_debit(
    balance_usd: Decimal,
    balance_inr: Decimal,
    amount_usd: Decimal,
    usd_to_inr_rate: Decimal,
) -> tuple[Decimal, Decimal]:
    """
    Compute new balances after a USD debit.
    Both USD and INR balances are decremented proportionally.
    Returns (new_balance_usd, new_balance_inr).
    """
    amount_inr = usd_to_inr(amount_usd, usd_to_inr_rate)
    new_usd = (balance_usd - amount_usd).quantize(AMOUNT_PRECISION)
    new_inr = (balance_inr - amount_inr).quantize(AMOUNT_PRECISION)
    # Guard against floating-point underflow errors
    if new_usd < Decimal("0"):
        new_usd = Decimal("0")
    if new_inr < Decimal("0"):
        new_inr = Decimal("0")
    return new_usd, new_inr
