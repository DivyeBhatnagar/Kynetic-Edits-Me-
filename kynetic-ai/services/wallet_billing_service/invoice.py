"""
GST Invoice generation — Phase 10.

Handles:
  - Invoice number sequencing: KYN/{fiscal_year}/{seq:06d}
  - GST calculation (18% default for SaaS/cloud services in India)
  - Invoice record creation in DB
  - PDF generation (async background task — stores placeholder URL initially)

Fiscal year: Indian fiscal year runs Apr 1 → Mar 31.
  e.g. Apr 2024–Mar 2025 → "2024-25"
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.billing_monitoring_models import Invoice, InvoiceSequence

if TYPE_CHECKING:
    pass

logger = structlog.get_logger(__name__)

# Indian GST rate for cloud/SaaS services (IGST for inter-state, CGST+SGST for intra-state)
# Simplified to IGST for digital services
GST_RATE = Decimal("0.18")
INVOICE_PREFIX = "KYN"


def _get_fiscal_year(dt: date | None = None) -> str:
    """
    Return the Indian fiscal year string for a given date.
    e.g. 2024-04-01 → "2024-25", 2025-01-15 → "2024-25"
    """
    d = dt or date.today()
    if d.month >= 4:
        return f"{d.year}-{str(d.year + 1)[-2:]}"
    return f"{d.year - 1}-{str(d.year)[-2:]}"


def calculate_gst(amount_inr: Decimal) -> tuple[Decimal, Decimal]:
    """
    Returns (base_amount_inr, gst_amount_inr) where:
      base + gst = amount_inr (inclusive GST calculation).

    Kynetic bills inclusive GST — the wallet top-up amount is GST-inclusive.
    Formula: base = total / (1 + rate), gst = total - base
    """
    rate = GST_RATE
    base = (amount_inr / (1 + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gst = (amount_inr - base).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return base, gst


async def next_invoice_number(session: AsyncSession, fiscal_year: str | None = None) -> str:
    """
    Atomically increment the invoice sequence for the given fiscal year
    and return the formatted invoice number.

    Uses a row-level lock (SELECT FOR UPDATE) to guarantee uniqueness under
    concurrent writes without a database sequence.

    Returns: "KYN/2024-25/000001"
    """
    fy = fiscal_year or _get_fiscal_year()

    # Try to get existing row (row-level lock)
    result = await session.execute(
        select(InvoiceSequence)
        .where(InvoiceSequence.fiscal_year == fy)
        .with_for_update()
    )
    row = result.scalar_one_or_none()

    if row is None:
        # First invoice of this fiscal year
        seq = InvoiceSequence(fiscal_year=fy, last_seq=1)
        session.add(seq)
        seq_num = 1
    else:
        row.last_seq += 1
        seq_num = row.last_seq

    return f"{INVOICE_PREFIX}/{fy}/{seq_num:06d}"


async def create_invoice(
    session: AsyncSession,
    *,
    transaction_id: uuid.UUID,
    user_id: uuid.UUID,
    amount_inr: Decimal,
    gstin: str | None = None,
) -> Invoice:
    """
    Create a GST invoice record for a completed India-region transaction.

    Steps:
      1. Compute GST (18% inclusive)
      2. Atomically get next invoice number
      3. Insert invoice row (pdf_url = None initially; populated by async task)

    The caller is responsible for committing the session.
    """
    _base, gst_amount = calculate_gst(amount_inr)

    invoice_number = await next_invoice_number(session)

    invoice = Invoice(
        id=uuid.uuid4(),
        transaction_id=transaction_id,
        user_id=user_id,
        invoice_number=invoice_number,
        gstin=gstin,
        amount_inr=str(amount_inr),
        gst_rate_pct="18.00",
        gst_amount_inr=str(gst_amount),
        pdf_url=None,          # Populated later by generate_invoice_pdf task
        issued_at=datetime.now(timezone.utc),
    )
    session.add(invoice)

    logger.info(
        "invoice_created",
        invoice_number=invoice_number,
        user_id=str(user_id),
        amount_inr=str(amount_inr),
        gst_amount_inr=str(gst_amount),
    )
    return invoice


async def get_invoice(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Invoice | None:
    """Fetch invoice by ID, scoped to the requesting user."""
    result = await session.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .where(Invoice.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_invoices(
    session: AsyncSession,
    user_id: uuid.UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Invoice], int]:
    """Paginated invoice list for a user."""
    from sqlalchemy import func, select

    total_result = await session.execute(
        select(func.count()).where(Invoice.user_id == user_id).select_from(Invoice)
    )
    total = total_result.scalar_one()

    items_result = await session.execute(
        select(Invoice)
        .where(Invoice.user_id == user_id)
        .order_by(Invoice.issued_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = list(items_result.scalars().all())
    return items, total


async def update_invoice_pdf_url(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    pdf_url: str,
) -> None:
    """Set the PDF URL on an invoice after async generation."""
    await session.execute(
        update(Invoice)
        .where(Invoice.id == invoice_id)
        .values(pdf_url=pdf_url)
    )
