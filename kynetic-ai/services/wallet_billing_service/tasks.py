"""
Wallet & Billing Service — Celery tasks.

Phase 3: stub only.
Phase 4: per-second billing tick will be added here once instances exist.
"""

from services.wallet_billing_service.celery_app import celery_app


@celery_app.task(name="services.wallet_billing_service.tasks.reconcile_stripe_events")
def reconcile_stripe_events(payment_intent_id: str, user_id: str, amount_usd: float) -> dict:
    """
    Async fallback task to credit a wallet from a Stripe event.
    Triggered by the webhook handler for reliability.
    Phase 3: the webhook handler handles this inline;
    this task is the retry fallback for failures.
    """
    import uuid
    from decimal import Decimal
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from libs.db_models.marketplace_models import Currency, TransactionType, Wallet
    from services.wallet_billing_service.config import get_settings
    from services.wallet_billing_service.repository import WalletRepository

    settings = get_settings()
    sync_url = settings.database_url.replace("+asyncpg", "")

    engine = create_engine(sync_url, pool_pre_ping=True)
    with Session(engine) as session:
        # Use sync repository pattern for Celery
        from sqlalchemy import select
        wallet = session.execute(
            select(Wallet).where(Wallet.user_id == uuid.UUID(user_id))
        ).scalar_one_or_none()

        if not wallet:
            return {"error": "wallet_not_found", "user_id": user_id}

        from libs.db_models.marketplace_models import WalletTransaction
        existing = session.execute(
            select(WalletTransaction).where(
                WalletTransaction.stripe_payment_intent_id == payment_intent_id
            )
        ).scalar_one_or_none()

        if existing:
            return {"skipped": "already_processed", "pi_id": payment_intent_id}

        from services.wallet_billing_service.billing import apply_topup, AMOUNT_PRECISION
        rate = Decimal(settings.usd_to_inr_rate)
        amount = Decimal(str(amount_usd)).quantize(AMOUNT_PRECISION)
        new_usd, new_inr = apply_topup(wallet.balance_usd, wallet.balance_inr, amount, rate)

        wallet.balance_usd = new_usd
        wallet.balance_inr = new_inr

        txn = WalletTransaction(
            wallet_id=wallet.id,
            transaction_type=TransactionType.topup,
            amount=amount,
            currency=Currency.usd,
            stripe_payment_intent_id=payment_intent_id,
            description=f"Wallet top-up via Stripe (fallback task, ${amount:.2f})",
            balance_after_usd=new_usd,
            balance_after_inr=new_inr,
        )
        session.add(txn)
        session.commit()

    return {"credited": True, "pi_id": payment_intent_id, "amount_usd": float(amount)}
