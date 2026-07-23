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


# ── Razorpay / UPI (Phase 10 — India payments) ────────────────────────────

class UpiTopupRequest(BaseModel):
    """
    Developer initiates a wallet top-up via UPI/Razorpay.
    Server creates a Razorpay order; frontend uses order_id with Razorpay Checkout.
    """
    amount_inr: Decimal = Field(..., gt=0, description="Top-up amount in INR (minimum ₹50)")


class UpiTopupResponse(BaseModel):
    razorpay_order_id: str         # Used by Razorpay Checkout on frontend
    amount_inr: Decimal
    amount_paise: int              # For Razorpay SDK
    razorpay_key_id: str           # Public key — safe to send to frontend
    currency: str = "INR"


class RazorpayWebhookVerify(BaseModel):
    """Payload for frontend to confirm a Razorpay payment."""
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


# ── Invoice (Phase 10 — GST) ──────────────────────────────────────────────

class InvoiceResponse(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    user_id: uuid.UUID
    invoice_number: str
    gstin: str | None
    amount_inr: str
    gst_rate_pct: str
    gst_amount_inr: str
    pdf_url: str | None
    issued_at: datetime

    class Config:
        from_attributes = True


class InvoiceListResponse(BaseModel):
    items: list[InvoiceResponse]
    total: int
    page: int
    page_size: int


# ── Notifications (Phase 10) ───────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: uuid.UUID
    notification_type: str
    channel: str
    title: str
    body: str
    payload: dict[str, Any] | None
    is_read: bool
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    total: int
    unread_count: int
    page: int
    page_size: int


class NotificationPreferenceResponse(BaseModel):
    email_enabled: bool
    sms_enabled: bool
    low_balance_threshold_usd: str

    class Config:
        from_attributes = True


class NotificationPreferenceUpdate(BaseModel):
    email_enabled: bool | None = None
    sms_enabled: bool | None = None
    low_balance_threshold_usd: str | None = None


# ── Support tickets (Phase 10) ────────────────────────────────────────────

class SupportTicketCreate(BaseModel):
    subject: str = Field(..., min_length=5, max_length=255)
    description: str = Field(..., min_length=10)
    region: str = "global"   # "india" or "global"


class SupportTicketResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    region: str
    subject: str
    status: str
    external_ticket_id: str | None
    created_at: datetime

    class Config:
        from_attributes = True
