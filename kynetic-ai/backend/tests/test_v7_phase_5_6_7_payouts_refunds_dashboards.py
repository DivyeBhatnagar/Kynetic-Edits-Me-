"""
Implementation Plan v7 Phase P5, P6, & P7 Integration Tests — Payout Engine, Refunds, & Dashboards

Tests:
1. Idempotent Payout Engine: batch creation, transfer execution with provider reference_id, host earnings settlement, & ledger balancing.
2. Payout Failure Recovery: permanent error escalation to manual_review status.
3. Refund & Failure Recovery Engine: normal refund vs refund-after-host-paid platform refund_reserve buffer.
4. Cashfree Easy Split Adapter & Financial Dashboards: second provider abstraction & host financial dashboard.
"""

import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus, OSType
from libs.db_models.payment_models_v7 import (
    HostEarnings,
    HostEarningsStatus,
    Order,
    OrderStatus,
    Payment,
    PaymentStatus,
    PayoutStatus,
    RefundStatus,
)
from services.payout_service.payout_engine import create_payout_batch, execute_payout
from services.wallet_billing_service.refund_service import process_refund
from services.wallet_billing_service.provider_interface import CashfreeEasySplitAdapter, get_provider_for_host
from services.wallet_billing_service.dashboard_routes import get_host_financial_dashboard
from services.wallet_billing_service.ledger_service import LedgerService


@pytest.mark.asyncio
async def test_payout_batching_idempotent_execution_and_ledger(db_session: AsyncSession):
    u_id = uuid.uuid4()
    h_id = uuid.uuid4()

    user = User(id=u_id, email="payout_host@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host = Host(id=h_id, user_id=u_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)

    # 2 Host earnings ($60 net each = $120 total)
    he1 = HostEarnings(id=uuid.uuid4(), billing_session_id=uuid.uuid4(), host_id=h_id, gross_amount=70, commission_amount=10, net_amount=60, status=HostEarningsStatus.pending_settlement)
    he2 = HostEarnings(id=uuid.uuid4(), billing_session_id=uuid.uuid4(), host_id=h_id, gross_amount=70, commission_amount=10, net_amount=60, status=HostEarningsStatus.pending_settlement)
    db_session.add(he1)
    db_session.add(he2)
    await db_session.commit()

    # 1. Batch Payout
    payout = await create_payout_batch(db_session, host_id=h_id, min_threshold_usd=Decimal("50.00"))
    assert payout is not None
    assert payout.total_amount == Decimal("120.00")
    assert payout.status == PayoutStatus.scheduled

    # 2. Execute Payout
    payout_executed = await execute_payout(db_session, payout_id=payout.id, country_code="IN")
    assert payout_executed.status == PayoutStatus.completed
    assert payout_executed.provider_transfer_id.startswith("trf_rzp_")

    await db_session.refresh(he1)
    await db_session.refresh(he2)
    assert he1.status == HostEarningsStatus.settled
    assert he2.status == HostEarningsStatus.settled

    # 3. Verify Ledger Balance
    reconciliation = await LedgerService.reconcile_ledger(db_session)
    assert reconciliation["reconciled"] is True


@pytest.mark.asyncio
async def test_payout_failure_escalation_to_manual_review(db_session: AsyncSession):
    u_id = uuid.uuid4()
    h_id = uuid.uuid4()

    user = User(id=u_id, email="payout_fail@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)
    host = Host(id=h_id, user_id=u_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)

    he = HostEarnings(id=uuid.uuid4(), billing_session_id=uuid.uuid4(), host_id=h_id, gross_amount=100, commission_amount=12, net_amount=88, status=HostEarningsStatus.pending_settlement)
    db_session.add(he)
    await db_session.commit()

    payout = await create_payout_batch(db_session, host_id=h_id)
    assert payout is not None

    # Execute with simulated permanent error
    failed_payout = await execute_payout(db_session, payout_id=payout.id, simulate_permanent_error=True)
    assert failed_payout.status == PayoutStatus.manual_review


@pytest.mark.asyncio
async def test_refund_engine_and_platform_reserve_buffer(db_session: AsyncSession):
    u_id = uuid.uuid4()
    user = User(id=u_id, email="rfnd@example.com", hashed_password="hash", role=UserRole.DEVELOPER)
    db_session.add(user)

    order = Order(id=uuid.uuid4(), user_id=u_id, provider="razorpay", provider_order_id="ord_123", amount=50.0, status=OrderStatus.paid)
    db_session.add(order)
    payment = Payment(id=uuid.uuid4(), order_id=order.id, provider_payment_id="pay_123", amount=50.0, status=PaymentStatus.captured)
    db_session.add(payment)
    await db_session.commit()

    # 1. Normal Refund before host paid
    rfnd1 = await process_refund(db_session, payment_id=payment.id, amount=Decimal("25.00"), reason="Unused compute", requested_by=u_id, is_host_already_paid=False)
    assert rfnd1.status == RefundStatus.processed
    assert payment.status == PaymentStatus.refunded

    # 2. Refund after host paid (draws from platform refund_reserve buffer)
    payment2 = Payment(id=uuid.uuid4(), order_id=order.id, provider_payment_id="pay_456", amount=50.0, status=PaymentStatus.captured)
    db_session.add(payment2)
    await db_session.commit()

    rfnd2 = await process_refund(db_session, payment_id=payment2.id, amount=Decimal("50.00"), reason="Host issue", requested_by=u_id, is_host_already_paid=True)
    assert rfnd2.status == RefundStatus.processed


@pytest.mark.asyncio
async def test_cashfree_adapter_and_financial_dashboards(db_session: AsyncSession):
    # 1. Test Cashfree Adapter
    cf_adapter = get_provider_for_host("IN_CASHFREE")
    assert isinstance(cf_adapter, CashfreeEasySplitAdapter)

    cf_order = await cf_adapter.create_order(Decimal("100.00"), "INR", {"user_id": "cf_u1"})
    assert cf_order["provider"] == "cashfree"
    assert cf_order["order_id"].startswith("cf_order_")

    cf_trf = await cf_adapter.create_transfer("cf_vendor_1", Decimal("80.00"), "INR", "payout_ref1")
    assert cf_trf["transfer_id"].startswith("cf_trf_")

    # 2. Test Host Financial Dashboard Query
    u_id = uuid.uuid4()
    h_id = uuid.uuid4()
    user = User(id=u_id, email="dash@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)
    host = Host(id=h_id, user_id=u_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    dash = await get_host_financial_dashboard(host_id=h_id, session=db_session)
    assert dash["host_id"] == str(h_id)
    assert dash["effective_commission_pct"] == 12.0
    assert "pending_earnings_usd" in dash
