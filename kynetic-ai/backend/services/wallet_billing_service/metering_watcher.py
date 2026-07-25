"""
Billing Service — Per-Second Direct Metering Watcher (metering_watcher.py)

Architecture:
- Metering debits active instance usage per-second directly to billing sessions and the double-entry financial ledger (§7).
- Recorded in append-only v7_ledger_entries (customer_account:{developer_id} -> platform_revenue).
"""

from decimal import Decimal
import uuid
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.provisioning_models import Instance, InstanceStatus
from services.wallet_billing_service.ledger_service import LedgerService

log = structlog.get_logger(__name__)


async def process_per_second_metering(session: AsyncSession, elapsed_seconds: int = 1) -> list[uuid.UUID]:
    """
    Meters active instance usage per-second and records double-entry ledger entries.
    Returns list of instance IDs that were terminated due to account status flags.
    """
    stmt = select(Instance).where(Instance.status == InstanceStatus.running)
    res = await session.execute(stmt)
    running_instances = list(res.scalars().all())

    terminated_instances = []

    for inst in running_instances:
        # Calculate debit amount
        charge = Decimal(str(inst.price_per_second_usd)) * Decimal(str(elapsed_seconds))
        inst.billed_seconds += elapsed_seconds

        # Record double-entry ledger entry (§7)
        await LedgerService.record_double_entry(
            session,
            entry_type="USAGE_DEBIT",
            account_debit=f"customer_account:{inst.developer_id}",
            account_credit="platform_revenue",
            amount_usd=charge,
            reference_type="instance",
            reference_id=inst.id,
        )

    await session.flush()
    return terminated_instances
