"""
Wallet & Billing Service — Priority-Based Commission Engine & Host Earnings Split (commission_service.py)

Architecture (§9):
- Priority order: promotional -> host -> enterprise -> workload -> gpu_type -> region -> global_default.
- Lower priority integer = higher precedence. First active valid rule wins.
- Session completion calculates commission and net host earnings, writing HostEarnings + balanced double-entry ledger entries.
"""

from decimal import Decimal
import uuid
from datetime import datetime, timezone
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.payment_models_v7 import (
    CommissionRule,
    CommissionScope,
    HostEarnings,
    HostEarningsStatus,
)
from services.wallet_billing_service.ledger_service import LedgerService

log = structlog.get_logger(__name__)

DEFAULT_GLOBAL_COMMISSION_PCT = Decimal("12.00")  # 12% platform fee default


class CommissionResolver:

    @staticmethod
    async def resolve_commission_rate(
        session: AsyncSession,
        host_id: uuid.UUID | None = None,
        gpu_model: str | None = None,
        region: str | None = None,
    ) -> tuple[Decimal, uuid.UUID | None]:
        """
        Resolves applicable commission percentage (§9).
        Evaluates active rules ordered by priority ASC.
        Returns (commission_pct, rule_id).
        """
        stmt = select(CommissionRule).where(CommissionRule.active == True).order_by(CommissionRule.priority.asc())
        res = await session.execute(stmt)
        rules = res.scalars().all()

        now_time = datetime.now(tz=timezone.utc)
        for rule in rules:
            if rule.valid_from and rule.valid_from > now_time:
                continue
            if rule.valid_until and rule.valid_until < now_time:
                continue

            if rule.scope == CommissionScope.promotional:
                return Decimal(str(rule.commission_pct)), rule.id
            elif rule.scope == CommissionScope.host and rule.scope_ref_id == str(host_id):
                return Decimal(str(rule.commission_pct)), rule.id
            elif rule.scope == CommissionScope.gpu_type and rule.scope_ref_id == gpu_model:
                return Decimal(str(rule.commission_pct)), rule.id
            elif rule.scope == CommissionScope.global_default:
                return Decimal(str(rule.commission_pct)), rule.id

        return DEFAULT_GLOBAL_COMMISSION_PCT, None

    @staticmethod
    async def finalize_session_commission(
        session: AsyncSession,
        billing_session_id: uuid.UUID,
        host_id: uuid.UUID,
        final_cost_usd: Decimal,
        gpu_model: str | None = None,
        region: str | None = None,
    ) -> HostEarnings:
        """
        Finalizes billing session charges, splits platform commission, creates HostEarnings record,
        and writes double-entry ledger records (§6, §7, §9).
        """
        comm_pct, rule_id = await CommissionResolver.resolve_commission_rate(session, host_id, gpu_model, region)

        comm_amount = (final_cost_usd * comm_pct / Decimal("100.00")).quantize(Decimal("0.0001"))
        net_amount = final_cost_usd - comm_amount

        earnings = HostEarnings(
            id=uuid.uuid4(),
            billing_session_id=billing_session_id,
            host_id=host_id,
            gross_amount=final_cost_usd,
            commission_amount=comm_amount,
            commission_rule_id=rule_id,
            net_amount=net_amount,
            currency="USD",
            status=HostEarningsStatus.pending_settlement,
        )
        session.add(earnings)

        # Double-entry ledger entries (§7):
        # 1. Platform revenue split
        await LedgerService.record_double_entry(
            session,
            entry_type="PLATFORM_COMMISSION",
            account_debit="platform_revenue",
            account_credit="platform_revenue_retained",
            amount_usd=comm_amount,
            reference_type="billing_session",
            reference_id=billing_session_id,
        )

        # 2. Host earnings accrued pending payout
        await LedgerService.record_double_entry(
            session,
            entry_type="HOST_EARNINGS",
            account_debit="platform_revenue",
            account_credit=f"host_payable:{host_id}",
            amount_usd=net_amount,
            reference_type="billing_session",
            reference_id=billing_session_id,
        )

        await session.flush()
        log.info(
            "commission.session_finalized",
            session_id=str(billing_session_id),
            host_id=str(host_id),
            gross=str(final_cost_usd),
            comm=str(comm_amount),
            net=str(net_amount),
            pct=str(comm_pct),
        )
        return earnings
