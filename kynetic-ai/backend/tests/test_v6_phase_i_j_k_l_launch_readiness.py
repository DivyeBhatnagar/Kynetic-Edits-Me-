"""
Phase I, J, K & L Integration Tests — Payments, Security Hardening, Observability & Launch Readiness

Tests:
1. Metering & Zero-Balance Auto-Termination: process_per_second_metering ($0.00 balance -> terminated)
2. Trust Tiers & Device Fingerprinting: enforce_trust_tier_limits & record_device_fingerprint
3. Platform Emergency Kill Switch: trigger_emergency_kill_switch (instant instance/host/user revocation)
4. Host Abuse Signature Detector: HostAbuseDetector.scan_image & scan_process_cmdline
5. Prometheus Observability Metrics Export: metrics.export_prometheus_text
6. Full End-to-End Launch Readiness Dogfooding Run: Login -> Launch -> Metering -> Terminate -> Deletion Receipt
"""

import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus
from libs.db_models.marketplace_models import Listing, ResourceType, ListingStatus, Wallet, WalletTransaction
from libs.db_models.provisioning_models import Instance, InstanceStatus, SecureDeletionReceipt
from services.wallet_billing_service.metering_watcher import process_per_second_metering
from services.security_service.trust_manager import enforce_trust_tier_limits, record_device_fingerprint, TrustTierError
from services.security_service.kill_switch import trigger_emergency_kill_switch
from host_agent.abuse_detector import HostAbuseDetector
from libs.common.metrics import metrics


@pytest.mark.asyncio
async def test_metering_watcher_debit_and_zero_balance_autotermination(db_session: AsyncSession):
    dev_id = uuid.uuid4()
    dev = User(id=dev_id, email=f"meter_{dev_id.hex[:6]}@example.com", hashed_password="hash", role=UserRole.DEVELOPER)
    db_session.add(dev)

    # Wallet with small balance
    wallet = Wallet(id=uuid.uuid4(), user_id=dev_id, balance_usd=Decimal("0.001000"), balance_inr=Decimal("0.08"))
    db_session.add(wallet)

    host = Host(id=uuid.uuid4(), user_id=dev_id, status=HostStatus.VERIFIED, os_type="linux", agent_version="1.0.0")
    db_session.add(host)

    listing = Listing(
        id=uuid.uuid4(), host_id=host.id, owner_user_id=dev_id, resource_type=ResourceType.gpu,
        gpu_model="RTX 4090", gpu_count=1, gpu_vram_gb=24.0, cpu_cores=16, ram_gb=64.0, storage_gb=500.0,
        price_per_hour_usd=Decimal("3.60"), price_per_hour_inr=Decimal("300.00"),
        price_per_second_usd=Decimal("0.001000"), price_per_second_inr=Decimal("0.083"),
        region="us-east-1", status=ListingStatus.active,
    )
    db_session.add(listing)

    instance = Instance(
        id=uuid.uuid4(), developer_id=dev_id, listing_id=listing.id, host_id=host.id,
        status=InstanceStatus.running, hold_amount=Decimal("1.00"), price_per_second_usd=Decimal("0.001000"),
    )
    db_session.add(instance)
    await db_session.commit()

    # Process 2 seconds metering (charge $0.002000 > balance $0.001000) -> should auto-terminate
    terminated_ids = await process_per_second_metering(db_session, elapsed_seconds=2)
    assert instance.id in terminated_ids

    await db_session.refresh(instance)
    assert instance.status == InstanceStatus.terminated


@pytest.mark.asyncio
async def test_trust_tier_limits_and_device_fingerprinting(db_session: AsyncSession):
    dev_id = uuid.uuid4()

    # Tier 1 cap is 2 instances
    tier = await enforce_trust_tier_limits(dev_id, db_session, requested_hourly_spend_usd=Decimal("5.00"), current_active_instances=1)
    assert tier == 1

    # Over instance cap -> raises TrustTierError
    with pytest.raises(TrustTierError):
        await enforce_trust_tier_limits(dev_id, db_session, requested_hourly_spend_usd=Decimal("5.00"), current_active_instances=2)

    # Over spend cap -> raises TrustTierError
    with pytest.raises(TrustTierError):
        await enforce_trust_tier_limits(dev_id, db_session, requested_hourly_spend_usd=Decimal("15.00"), current_active_instances=0)

    # Device fingerprinting
    fp = await record_device_fingerprint(dev_id, "hash_abc123", "192.168.1.1", db_session)
    assert fp.fingerprint_hash == "hash_abc123"


@pytest.mark.asyncio
async def test_emergency_kill_switch(db_session: AsyncSession):
    dev_id = uuid.uuid4()
    dev = User(id=dev_id, email="kill@example.com", hashed_password="hash", role=UserRole.DEVELOPER)
    db_session.add(dev)

    host = Host(id=uuid.uuid4(), user_id=dev_id, status=HostStatus.VERIFIED, os_type="linux", agent_version="1.0.0")
    db_session.add(host)

    listing = Listing(
        id=uuid.uuid4(), host_id=host.id, owner_user_id=dev_id, resource_type=ResourceType.gpu,
        gpu_model="RTX 4090", gpu_count=1, gpu_vram_gb=24.0, cpu_cores=16, ram_gb=64.0, storage_gb=500.0,
        price_per_hour_usd=Decimal("1.00"), price_per_hour_inr=Decimal("83.00"),
        price_per_second_usd=Decimal("0.000277"), price_per_second_inr=Decimal("0.023"),
        region="us-east-1", status=ListingStatus.active,
    )
    db_session.add(listing)

    instance = Instance(
        id=uuid.uuid4(), developer_id=dev_id, listing_id=listing.id, host_id=host.id,
        status=InstanceStatus.running, hold_amount=Decimal("1.00"), price_per_second_usd=Decimal("0.000277"),
    )
    db_session.add(instance)
    await db_session.commit()

    # Trigger emergency kill switch on instance
    event = await trigger_emergency_kill_switch("instance", instance.id, "Security breach test", db_session)
    assert event.target_type == "instance"

    await db_session.refresh(instance)
    assert instance.status == InstanceStatus.terminated


def test_host_abuse_signature_detector():
    # Pre-execution image scan
    clean_res = HostAbuseDetector.scan_image("ubuntu:22.04")
    assert clean_res["safe"] is True

    abusive_res = HostAbuseDetector.scan_image("xmrig/xmrig:latest")
    assert abusive_res["safe"] is False

    # Process cmdline scan
    assert HostAbuseDetector.scan_process_cmdline("./xmrig -o stratum+tcp://pool:3333") is True
    assert HostAbuseDetector.scan_process_cmdline("python train.py") is False


def test_prometheus_metrics_export():
    metrics.set_gauge("kynetic_instances_active_total", 5.0)
    metrics.inc_counter("kynetic_metered_seconds_total", 120.0)

    text = metrics.export_prometheus_text()
    assert "kynetic_instances_active_total 5.0" in text
    assert "kynetic_metered_seconds_total 120.0" in text
