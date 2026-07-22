"""
Wallet & Billing Service — Stripe SDK wrapper.

Wraps the Stripe Python SDK to provide:
  - PaymentIntent creation (developer top-ups)
  - Stripe Connect account creation (host payouts)
  - Webhook signature verification
  - Customer creation on signup

All calls are synchronous (stripe SDK is sync). Route handlers call
these from an asyncio executor (run_in_executor) to avoid blocking.
"""

from decimal import Decimal
from typing import Any

import stripe
import structlog

logger = structlog.get_logger(__name__)


def init_stripe(secret_key: str) -> None:
    """Initialize the Stripe client with the secret key."""
    stripe.api_key = secret_key


def create_payment_intent(
    amount_usd: Decimal,
    stripe_customer_id: str | None = None,
    metadata: dict[str, str] | None = None,
) -> stripe.PaymentIntent:
    """
    Create a Stripe PaymentIntent for a wallet top-up.

    amount_usd is converted to cents (integer, USD).
    Returns the PaymentIntent object. The frontend uses
    `payment_intent.client_secret` with Stripe.js to confirm.
    """
    amount_cents = int((amount_usd * 100).to_integral_value())  # USD cents
    params: dict[str, Any] = {
        "amount": amount_cents,
        "currency": "usd",
        "automatic_payment_methods": {"enabled": True},
        "metadata": metadata or {},
    }
    if stripe_customer_id:
        params["customer"] = stripe_customer_id

    intent = stripe.PaymentIntent.create(**params)
    logger.info(
        "stripe_payment_intent_created",
        payment_intent_id=intent.id,
        amount_cents=amount_cents,
    )
    return intent


def create_customer(
    email: str,
    user_id: str,
    metadata: dict[str, str] | None = None,
) -> stripe.Customer:
    """Create a Stripe Customer for a new developer."""
    customer = stripe.Customer.create(
        email=email,
        metadata={"kynetic_user_id": user_id, **(metadata or {})},
    )
    logger.info("stripe_customer_created", customer_id=customer.id, user_id=user_id)
    return customer


def create_connect_account(
    email: str,
    user_id: str,
    country: str = "US",
) -> stripe.Account:
    """
    Create a Stripe Connect Express account for a host.
    The host must complete Stripe's hosted onboarding flow.
    """
    account = stripe.Account.create(
        type="express",
        country=country,
        email=email,
        capabilities={
            "transfers": {"requested": True},
        },
        metadata={"kynetic_user_id": user_id},
    )
    logger.info(
        "stripe_connect_account_created",
        account_id=account.id,
        user_id=user_id,
    )
    return account


def create_connect_onboarding_link(
    account_id: str,
    refresh_url: str,
    return_url: str,
) -> str:
    """
    Generate a Stripe Connect Account Link for the host onboarding flow.
    Returns the URL string to redirect the host to.
    """
    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return link.url


def verify_webhook_signature(
    payload: bytes,
    sig_header: str,
    webhook_secret: str,
) -> stripe.Event:
    """
    Verify the Stripe webhook signature and return the parsed Event.
    Raises stripe.error.SignatureVerificationError on invalid signature.
    """
    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=sig_header,
        secret=webhook_secret,
    )
    return event
