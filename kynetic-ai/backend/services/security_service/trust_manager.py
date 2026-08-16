"""
Security Service — Progressive Trust Tiers & Device Fingerprinting (trust_manager.py)

Enforces security rules (§14):
1. Progressive Trust Tiers: Caps instance count and hourly spend for unverified developer accounts.
   - Tier 1: $10.00/hr max spend, max 2 instances.
   - Tier 2: $50.00/hr max spend, max 5 instances.
   - Tier 3: Unlimited spend, max 20 instances.
2. Device Fingerprinting: Stores SHA-256 fingerprint of device attributes at login.
"""

from decimal import Decimal
import uuid
import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.security_models import DeviceFingerprint, TrustTier

log = structlog.get_logger(__name__)

TIER_CAPS = {
    1: {"max_hourly_spend_usd": Decimal("10.00"), "max_instances": 2},
    2: {"max_hourly_spend_usd": Decimal("50.00"), "max_instances": 5},
    3: {"max_hourly_spend_usd": Decimal("1000.00"), "max_instances": 20},
}


class TrustTierError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def enforce_trust_tier_limits(
    user_id: uuid.UUID,
    session: AsyncSession,
    requested_hourly_spend_usd: Decimal = Decimal("1.00"),
    current_active_instances: int = 0,
) -> int:
    """
    Validates developer account against trust tier spend and instance caps.
    Raises TrustTierError if request exceeds trust tier limits.
    """
    stmt = select(TrustTier).where(TrustTier.user_id == user_id)
    res = await session.execute(stmt)
    tier_rec = res.scalar_one_or_none()

    tier_level = tier_rec.tier if tier_rec else 1
    caps = TIER_CAPS.get(tier_level, TIER_CAPS[1])

    if current_active_instances + 1 > caps["max_instances"]:
        log.warning("security.trust_tier_instance_cap_exceeded", user_id=str(user_id), tier=tier_level)
        raise TrustTierError(f"Trust Tier {tier_level} account limit reached ({caps['max_instances']} instances max). Upgrade account to expand limit.")

    if requested_hourly_spend_usd > caps["max_hourly_spend_usd"]:
        log.warning("security.trust_tier_spend_cap_exceeded", user_id=str(user_id), tier=tier_level)
        raise TrustTierError(f"Trust Tier {tier_level} max hourly spend cap (${caps['max_hourly_spend_usd']}/hr) exceeded.")

    return tier_level


async def record_device_fingerprint(
    user_id: uuid.UUID,
    device_hash: str,
    ip_address: str,
    session: AsyncSession,
) -> DeviceFingerprint:
    """Records device fingerprint snapshot on user login."""
    fp = DeviceFingerprint(
        id=uuid.uuid4(),
        user_id=user_id,
        fingerprint_hash=device_hash,
        ip_address=ip_address,
    )
    session.add(fp)
    await session.flush()
    log.info("security.device_fingerprint_recorded", user_id=str(user_id), ip=ip_address)
    return fp


def calculate_host_trust_score(
    attestation_status: str,
    secure_boot_compliant: bool = True,
    measured_boot_compliant: bool = True,
    kernel_version_fresh: bool = True,
    agent_version_fresh: bool = True,
    container_runtime_fresh: bool = True,
    gpu_driver_fresh: bool = True,
    network_anomalies_penalty: float = 0.0,
    prior_incidents_penalty: float = 0.0,
    abuse_violations_penalty: float = 0.0,
) -> tuple[float, str]:
    """
    Computes Part 6 Composite Host Trust Score (0-100) and maps to Risk Band.

    Weights (Part 6.1):
      Attestation status:               25%
      Secure Boot + measured boot:      15%
      Kernel version freshness:         10%
      Host Agent version freshness:     10%
      Container runtime version:         5%
      GPU driver version:                5%
      Network behavior anomalies:       10%
      Prior security incidents:         10%
      Workload abuse violations:        10%

    Hard Gate Rule (Part 6.3):
      Attestation failure or expiry caps composite score at 29.0 (CRITICAL) regardless of other inputs.
    """
    # 1. Attestation weight (25%)
    attest_pts = 25.0 if attestation_status == "current" else 0.0

    # 2. Secure Boot + Measured Boot (15%)
    boot_pts = 0.0
    if secure_boot_compliant:
        boot_pts += 7.5
    if measured_boot_compliant:
        boot_pts += 7.5

    # 3. Software Component Freshness (30% total)
    kernel_pts = 10.0 if kernel_version_fresh else 3.0
    agent_pts = 10.0 if agent_version_fresh else 3.0
    runtime_pts = 5.0 if container_runtime_fresh else 1.0
    gpu_pts = 5.0 if gpu_driver_fresh else 1.0

    # 4. Behavioral & Historical Anomaly Deductions (30% total baseline)
    network_pts = max(0.0, 10.0 - network_anomalies_penalty)
    incident_pts = max(0.0, 10.0 - prior_incidents_penalty)
    abuse_pts = max(0.0, 10.0 - abuse_violations_penalty)

    raw_score = (
        attest_pts
        + boot_pts
        + kernel_pts
        + agent_pts
        + runtime_pts
        + gpu_pts
        + network_pts
        + incident_pts
        + abuse_pts
    )

    # Enforce Hard Gate Rule (Part 6.3)
    if attestation_status in ("failed", "expired", "unattested"):
        final_score = min(29.0, raw_score)
    else:
        final_score = min(100.0, max(0.0, raw_score))

    # Risk Band Mapping (Part 6.2)
    if final_score >= 80.0:
        risk_band = "LOW_RISK"
    elif final_score >= 60.0:
        risk_band = "MEDIUM_RISK"
    elif final_score >= 30.0:
        risk_band = "HIGH_RISK"
    else:
        risk_band = "CRITICAL"

    log.debug(
        "trust_manager.score_calculated",
        attestation_status=attestation_status,
        score=final_score,
        risk_band=risk_band,
    )
    return round(final_score, 2), risk_band
