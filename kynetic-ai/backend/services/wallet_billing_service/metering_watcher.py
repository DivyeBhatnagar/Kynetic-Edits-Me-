"""
Wallet & Billing Service — Per-Second Metering Ticker & Zero-Balance Auto-Termination Watcher (metering_watcher.py)

Security & Billing Rules:
- Metering debits wallet balance per-second for all currently running instances.
- Transaction writes are recorded in the append-only wallet_transactions ledger.
- If developer wallet balance drops to $0.00, the instance is automatically transitioned to 'terminated' to prevent unpaid compute drain.
"""

from decimal import Decimal
import uuid
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.provisioning_models import Instance, InstanceStatus
from libs.db_models.marketplace_models import Wallet, WalletTransaction, TransactionType

log = structlog.get_logger(__name__)


async def process_per_second_metering(session: AsyncSession, elapsed_seconds: int = 1) -> list[uuid.UUID]:
    """
    Debits active instance usage from developer wallet.
    Returns list of instance IDs that were auto-terminated due to zero balance.
    """
    stmt = select(Instance).where(Instance.status == InstanceStatus.running)
    res = await session.execute(stmt)
    running_instances = list(res.scalars().all())

    terminated_instances = []

    for inst in running_instances:
        # Calculate debit amount
        charge = Decimal(str(inst.price_per_second_usd)) * Decimal(str(elapsed_seconds))
        
        # Query developer wallet
        w_stmt = select(Wallet).where(Wallet.user_id == inst.developer_id)
        w_res = await session.execute(w_stmt)
        wallet = w_res.scalar_one_or_none()

        if not wallet:
            log.warning("metering.wallet_not_found", developer_id=str(inst.developer_id), instance_id=str(inst.id))
            continue

        if wallet.balance_usd < charge or wallet.balance_usd <= Decimal("0.000000"):
            log.warning("metering.zero_balance_auto_termination", developer_id=str(inst.developer_id), instance_id=str(inst.id), balance=str(wallet.balance_usd))
            inst.status = InstanceStatus.terminated
            inst.hold_released = True
            terminated_instances.append(inst.id)
        else:
            wallet.balance_usd -= charge
            inst.billed_seconds += elapsed_seconds

            # Write ledger transaction
            tx = WalletTransaction(
                id=uuid.uuid4(),
                wallet_id=wallet.id,
                transaction_type=TransactionType.debit,
                amount_usd=charge,
                description=f"Per-second compute rental debit (Instance {inst.id})",
            )
            session.add(tx)

    await session.flush()
    return terminated_instances
