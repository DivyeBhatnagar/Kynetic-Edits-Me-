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
