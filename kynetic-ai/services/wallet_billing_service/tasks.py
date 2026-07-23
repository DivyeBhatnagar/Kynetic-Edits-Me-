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


# ── Phase 10: GST Invoice generation ──────────────────────────────────────

@celery_app.task(
    name="services.wallet_billing_service.tasks.generate_gst_invoice",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def generate_gst_invoice(
    self,
    transaction_id: str,
    user_id: str,
    amount_inr: float,
    gstin: str | None = None,
) -> dict:
    """
    Generate a GST-compliant invoice for an India-region transaction.

    Called by:
      - Razorpay webhook handler after a successful UPI payment
      - Any India-region billing event that needs a GST invoice

    Steps:
      1. Create Invoice record (with sequential invoice number)
      2. Enqueue PDF generation (generate_invoice_pdf task)
      3. Enqueue invoice_ready notification

    Phase 10: PDF generation is stubbed — pdf_url set after a background
    task completes. In production, use a PDF library (ReportLab/WeasyPrint)
    and upload to S3.
    """
    import uuid
    from decimal import Decimal
    import asyncio
    import structlog

    log = structlog.get_logger(__name__)

    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from libs.db_models.billing_monitoring_models import Invoice, InvoiceSequence
        from services.wallet_billing_service.config import get_settings
        from services.wallet_billing_service.invoice import (
            _get_fiscal_year,
            calculate_gst,
            INVOICE_PREFIX,
        )

        settings = get_settings()
        sync_url = settings.database_url.replace("+asyncpg", "")
        engine = create_engine(sync_url, pool_pre_ping=True)

        _txn_id = uuid.UUID(transaction_id)
        _user_id = uuid.UUID(user_id)
        _amount_inr = Decimal(str(amount_inr))
        _base, _gst = calculate_gst(_amount_inr)

        with Session(engine) as session:
            with session.begin():
                # Get/create fiscal year sequence (row-level lock via sync session)
                fy = _get_fiscal_year()
                seq_row = session.execute(
                    select(InvoiceSequence)
                    .where(InvoiceSequence.fiscal_year == fy)
                    .with_for_update()
                ).scalar_one_or_none()

                if seq_row is None:
                    seq_row = InvoiceSequence(fiscal_year=fy, last_seq=1)
                    session.add(seq_row)
                    seq_num = 1
                else:
                    seq_row.last_seq += 1
                    seq_num = seq_row.last_seq

                invoice_number = f"{INVOICE_PREFIX}/{fy}/{seq_num:06d}"

                inv = Invoice(
                    id=uuid.uuid4(),
                    transaction_id=_txn_id,
                    user_id=_user_id,
                    invoice_number=invoice_number,
                    gstin=gstin,
                    amount_inr=str(_amount_inr),
                    gst_rate_pct="18.00",
                    gst_amount_inr=str(_gst),
                    pdf_url=None,
                )
                session.add(inv)
                invoice_id = str(inv.id)

        log.info(
            "gst_invoice_generated",
            invoice_number=invoice_number,
            user_id=user_id,
            transaction_id=transaction_id,
        )

        # Enqueue PDF generation (non-blocking)
        generate_invoice_pdf.delay(invoice_id=invoice_id, invoice_number=invoice_number)

        return {
            "invoice_id": invoice_id,
            "invoice_number": invoice_number,
            "amount_inr": amount_inr,
            "gst_amount_inr": float(_gst),
        }

    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.wallet_billing_service.tasks.generate_invoice_pdf",
    bind=True,
    max_retries=2,
)
def generate_invoice_pdf(self, invoice_id: str, invoice_number: str) -> dict:
    """
    Async PDF generation for a GST invoice.

    Phase 10 stub: generates a placeholder pdf_url.
    Production: use ReportLab / WeasyPrint to generate PDF, upload to S3,
    update invoice.pdf_url, then fire invoice_ready notification.
    """
    import structlog
    log = structlog.get_logger(__name__)

    # Stub: in production, generate real PDF here
    pdf_url = f"https://storage.kynetic.ai/invoices/{invoice_id}.pdf"

    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy import update as sa_update
        from libs.db_models.billing_monitoring_models import Invoice
        from services.wallet_billing_service.config import get_settings

        settings = get_settings()
        sync_url = settings.database_url.replace("+asyncpg", "")
        engine = create_engine(sync_url, pool_pre_ping=True)

        import uuid
        with Session(engine) as session:
            with session.begin():
                session.execute(
                    sa_update(Invoice)
                    .where(Invoice.id == uuid.UUID(invoice_id))
                    .values(pdf_url=pdf_url)
                )

        log.info("invoice_pdf_generated", invoice_id=invoice_id, pdf_url=pdf_url)
        return {"invoice_id": invoice_id, "pdf_url": pdf_url}

    except Exception as exc:
        raise self.retry(exc=exc)
