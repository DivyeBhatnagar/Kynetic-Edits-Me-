"""
Implementation Plan v7 Phase P3 & Phase P4 Integration Tests — Host KYC & Commission Engine

Tests:
1. Host Financial Onboarding & KYC: application-layer encryption, state machine, linked account creation upon admin approval.
2. Priority-Based Commission Engine: rule resolution (promotional override vs global default), host earnings split, and double-entry ledger balancing.
"""

import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus, OSType
from libs.db_models.payment_models_v7 import (
    CommissionRule,
    CommissionScope,
    HostEarningsStatus,
    KYCStatus,
    ProviderAccountStatus,
)
from services.host_service.kyc_service import submit_host_kyc, approve_host_kyc
from services.wallet_billing_service.commission_service import CommissionResolver
from services.wallet_billing_service.ledger_service import LedgerService


@pytest.mark.asyncio
async def test_host_kyc_onboarding_and_linked_account_approval(db_session: AsyncSession):
    # Setup Host
    u_id = uuid.uuid4()
    h_id = uuid.uuid4()

    user = User(id=u_id, email="host_kyc@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host = Host(id=h_id, user_id=u_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    # 1. Submit KYC
    kyc_rec = await submit_host_kyc(
        db_session,
        host_id=h_id,
        pan_number="ABCDE1234F",
        bank_account_number="987654321012",
        ifsc_code="SBIN0001234",
        upi_id="host@upi",
    )
    assert kyc_rec.status == KYCStatus.pending
    assert kyc_rec.pan_number_encrypted.startswith("enc_v1_")
    assert kyc_rec.bank_account_number_encrypted.startswith("enc_v1_")

    # 2. Admin Approve KYC -> Creates Provider Linked Account
    p_acct = await approve_host_kyc(db_session, host_id=h_id, country_code="IN")
    assert p_acct.account_status == ProviderAccountStatus.active
    assert p_acct.linked_account_id.startswith("acc_rzp_")


@pytest.mark.asyncio
async def test_priority_commission_resolution_and_host_earnings_split(db_session: AsyncSession):
    u_id = uuid.uuid4()
    h_id = uuid.uuid4()
    session_id = uuid.uuid4()

    user = User(id=u_id, email="host_comm@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host = Host(id=h_id, user_id=u_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)

    # Add 5% Promotional Override Rule (priority=10)
    promo_rule = CommissionRule(
        id=uuid.uuid4(),
        scope=CommissionScope.promotional,
        commission_pct=5.00,
        priority=10,
        active=True,
    )
    db_session.add(promo_rule)
    await db_session.commit()

    # 1. Test Priority Resolution
    pct, rule_id = await CommissionResolver.resolve_commission_rate(db_session, host_id=h_id)
    assert pct == Decimal("5.00")
    assert rule_id == promo_rule.id

    # 2. Finalize Rental Session ($100 gross rental)
    gross_cost = Decimal("100.00")
    earnings = await CommissionResolver.finalize_session_commission(
        db_session,
        billing_session_id=session_id,
        host_id=h_id,
        final_cost_usd=gross_cost,
    )

    assert earnings.gross_amount == gross_cost
    assert earnings.commission_amount == Decimal("5.00")  # 5% of $100
    assert earnings.net_amount == Decimal("95.00")        # $95 net to host
    assert earnings.status == HostEarningsStatus.pending_settlement

    # 3. Verify Ledger Balance
    reconciliation = await LedgerService.reconcile_ledger(db_session)
    assert reconciliation["reconciled"] is True
    assert reconciliation["discrepancy_usd"] == 0.0
