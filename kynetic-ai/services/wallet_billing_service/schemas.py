"""
Wallet & Billing Service — Pydantic schemas.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from libs.db_models.marketplace_models import Currency, TransactionType


# ── Wallet ─────────────────────────────────────────────────────────────────

class WalletResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    balance_usd: Decimal
    balance_inr: Decimal
    preferred_currency: Currency
    created_at: datetime

    class Config:
        from_attributes = True


class WalletBalanceResponse(BaseModel):
    """Simplified balance response — the primary field is in the user's preferred currency."""
    wallet_id: uuid.UUID
    preferred_currency: Currency
    balance: Decimal          # In preferred_currency
    balance_usd: Decimal      # Always USD
    balance_inr: Decimal      # Always INR


# ── Top-up ─────────────────────────────────────────────────────────────────

class TopupRequest(BaseModel):
    """
    Developer initiates a wallet top-up.
    The server creates a Stripe PaymentIntent and returns the client_secret
    for the frontend to confirm via Stripe.js / Stripe Elements.
    """
    amount_usd: Decimal = Field(..., gt=0, description="Top-up amount in USD")
    currency: Currency = Currency.usd


class TopupResponse(BaseModel):
    """Returned to frontend — Stripe PaymentIntent details."""
    payment_intent_id: str
    client_secret: str          # Used by Stripe.js to confirm the payment
    amount_usd: Decimal
    amount_inr: Decimal         # For display in INR preference UIs
    stripe_publishable_key: str


# ── Transactions ───────────────────────────────────────────────────────────

class TransactionResponse(BaseModel):
    id: uuid.UUID
    wallet_id: uuid.UUID
    transaction_type: TransactionType
    amount: Decimal
    currency: Currency
    stripe_payment_intent_id: str | None
    description: str | None
    balance_after_usd: Decimal
    balance_after_inr: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int
    page: int
    page_size: int


# ── Stripe webhooks ────────────────────────────────────────────────────────

class StripeWebhookPayload(BaseModel):
    """Raw Stripe event — validated by signature, parsed by stripe SDK."""
    id: str
    type: str
    data: dict[str, Any]
