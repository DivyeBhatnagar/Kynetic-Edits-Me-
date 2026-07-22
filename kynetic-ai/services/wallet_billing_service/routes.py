"""
Wallet & Billing Service — API routes.

Endpoints:
  GET  /wallet/balance             current balance in preferred currency
  GET  /wallet/transactions        paginated transaction history
  POST /wallet/topup               create Stripe PaymentIntent → return client_secret
  POST /billing/webhooks/stripe    Stripe event handler (NO JWT — signature verified)
"""

import asyncio
import uuid
from decimal import Decimal

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from libs.common.auth import require_auth
from libs.common.database import get_db_session
from libs.db_models.marketplace_models import Currency, TransactionType
from services.wallet_billing_service import stripe_client as sc
from services.wallet_billing_service.billing import InsufficientFundsError, usd_to_inr
from services.wallet_billing_service.config import get_settings
from services.wallet_billing_service.repository import StripeAccountRepository, WalletRepository
from services.wallet_billing_service.schemas import (
    TopupRequest,
    TopupResponse,
    TransactionListResponse,
    TransactionResponse,
    WalletBalanceResponse,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Initialize Stripe on module load
sc.init_stripe(settings.stripe_secret_key)

wallet_router = APIRouter(prefix="/wallet", tags=["Wallet"])
billing_router = APIRouter(prefix="/billing", tags=["Billing"])


# ── GET /wallet/balance ────────────────────────────────────────────────────

@wallet_router.get("/balance", response_model=WalletBalanceResponse)
async def get_balance(
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    user_id = uuid.UUID(auth["sub"])
    repo = WalletRepository(session)
    wallet = await repo.get_by_user_id(user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    fx_rate = Decimal(settings.usd_to_inr_rate)
    balance = (
        wallet.balance_usd
        if wallet.preferred_currency == Currency.usd
        else wallet.balance_inr
    )
    return WalletBalanceResponse(
        wallet_id=wallet.id,
        preferred_currency=wallet.preferred_currency,
        balance=balance,
        balance_usd=wallet.balance_usd,
        balance_inr=wallet.balance_inr,
    )


# ── GET /wallet/transactions ───────────────────────────────────────────────

@wallet_router.get("/transactions", response_model=TransactionListResponse)
async def list_transactions(
    page: int = 1,
    page_size: int = 20,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    user_id = uuid.UUID(auth["sub"])
    repo = WalletRepository(session)
    wallet = await repo.get_by_user_id(user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    txns, total = await repo.get_transactions(wallet.id, page=page, page_size=page_size)
    return TransactionListResponse(
        items=[TransactionResponse.model_validate(t) for t in txns],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── POST /wallet/topup ────────────────────────────────────────────────────

@wallet_router.post("/topup", response_model=TopupResponse)
async def topup_wallet(
    body: TopupRequest,
    auth: dict = Depends(require_auth),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Create a Stripe PaymentIntent for a wallet top-up.

    Returns a `client_secret` that the frontend uses with Stripe.js to
    confirm the payment. The actual wallet credit happens when Stripe
    fires `payment_intent.succeeded` to our webhook endpoint.
    """
    user_id = uuid.UUID(auth["sub"])
    wallet_repo = WalletRepository(session)
    stripe_repo = StripeAccountRepository(session)

    wallet = await wallet_repo.get_by_user_id(user_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found.")

    stripe_acct = await stripe_repo.get_by_user_id(user_id)
    customer_id = stripe_acct.stripe_customer_id if stripe_acct else None

    # Create Stripe PaymentIntent (run sync Stripe SDK in executor)
    loop = asyncio.get_event_loop()
    try:
        intent = await loop.run_in_executor(
            None,
            lambda: sc.create_payment_intent(
                amount_usd=body.amount_usd,
                stripe_customer_id=customer_id,
                metadata={"kynetic_user_id": str(user_id), "wallet_id": str(wallet.id)},
            ),
        )
    except Exception as exc:
        logger.error("stripe_payment_intent_creation_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment service unavailable. Try again later.",
        )

    fx_rate = Decimal(settings.usd_to_inr_rate)
    amount_inr = usd_to_inr(body.amount_usd, fx_rate)

    logger.info(
        "topup_intent_created",
        user_id=str(user_id),
        amount_usd=float(body.amount_usd),
        payment_intent_id=intent.id,
    )
    return TopupResponse(
        payment_intent_id=intent.id,
        client_secret=intent.client_secret,
        amount_usd=body.amount_usd,
        amount_inr=amount_inr,
        stripe_publishable_key=settings.stripe_publishable_key,
    )


# ── POST /billing/webhooks/stripe ─────────────────────────────────────────

@billing_router.post("/webhooks/stripe", status_code=status.HTTP_200_OK)
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="stripe-signature"),
    session: AsyncSession = Depends(get_db_session),
):
    """
    Stripe webhook handler.

    IMPORTANT: This endpoint must NOT require JWT auth — Stripe POSTs here.
    Security: Stripe-Signature header verified via HMAC (stripe.Webhook.construct_event).

    Handled events:
      payment_intent.succeeded → credit developer wallet
      account.updated          → update Connect account onboarding status
    """
    payload = await request.body()

    # Verify Stripe signature
    loop = asyncio.get_event_loop()
    try:
        event = await loop.run_in_executor(
            None,
            lambda: sc.verify_webhook_signature(
                payload, stripe_signature or "", settings.stripe_webhook_secret
            ),
        )
    except Exception as exc:
        logger.warning("stripe_webhook_signature_invalid", error=str(exc))
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")

    event_type = event["type"]
    logger.info("stripe_webhook_received", event_type=event_type, event_id=event["id"])

    wallet_repo = WalletRepository(session)
    stripe_repo = StripeAccountRepository(session)
    fx_rate = Decimal(settings.usd_to_inr_rate)

    # ── payment_intent.succeeded → credit wallet ──────────────────────────
    if event_type == "payment_intent.succeeded":
        pi = event["data"]["object"]
        payment_intent_id: str = pi["id"]
        amount_cents: int = pi["amount"]
        amount_usd = Decimal(str(amount_cents)) / Decimal("100")
        kynetic_user_id = pi.get("metadata", {}).get("kynetic_user_id")

        if not kynetic_user_id:
            logger.warning("stripe_pi_missing_user_id", pi_id=payment_intent_id)
            return {"received": True}

        user_id = uuid.UUID(kynetic_user_id)
        wallet = await wallet_repo.get_by_user_id(user_id)
        if not wallet:
            logger.error("stripe_pi_wallet_not_found", user_id=str(user_id))
            return {"received": True}

        # Idempotency: skip if already processed
        existing = await wallet_repo.get_transaction_by_stripe_pi(payment_intent_id)
        if existing:
            logger.info("stripe_pi_already_processed", pi_id=payment_intent_id)
            return {"received": True}

        await wallet_repo.create_transaction(
            wallet=wallet,
            transaction_type=TransactionType.topup,
            amount=amount_usd,
            currency=Currency.usd,
            usd_to_inr_rate=fx_rate,
            stripe_payment_intent_id=payment_intent_id,
            description=f"Wallet top-up via Stripe (${amount_usd:.2f})",
        )
        await session.commit()
        logger.info(
            "wallet_credited",
            user_id=str(user_id),
            amount_usd=float(amount_usd),
            pi_id=payment_intent_id,
        )

    # ── account.updated → sync Connect onboarding status ──────────────────
    elif event_type == "account.updated":
        acct = event["data"]["object"]
        connect_id: str = acct["id"]
        charges_enabled: bool = acct.get("charges_enabled", False)
        kynetic_user_id = acct.get("metadata", {}).get("kynetic_user_id")

        if kynetic_user_id:
            user_id = uuid.UUID(kynetic_user_id)
            stripe_acct = await stripe_repo.get_by_user_id(user_id)
            if stripe_acct:
                await stripe_repo.update_connect_account(
                    stripe_acct, connect_id, onboarding_complete=charges_enabled
                )
                await session.commit()
                logger.info(
                    "connect_account_updated",
                    user_id=str(user_id),
                    charges_enabled=charges_enabled,
                )

    return {"received": True}
