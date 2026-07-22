"""
Security Service — Trust Tier Enforcement.

Determines whether a user's current trust tier permits a requested operation.
Called by the provisioning_service before launching any instance.

Trust tier defaults:
  unverified: max 2 vCPUs, no GPU, 10 GPU-hours/month, $50/month spend
  tier1 (phone):  max 8 vCPUs, 8 GB VRAM, 50 GPU-hours, $200/month
  tier2 (gov ID): max 32 vCPUs, 48 GB VRAM, 500 GPU-hours, $2000/month
  tier3 (admin):  no caps

Caps are stored in the trust_tiers table and enforced here.
NULL cap value always means "no cap" (only tier3 defaults to all NULL).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import structlog

from libs.db_models.security_models import TrustTierLevel
from services.security_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


# Tier defaults applied when creating a new TrustTier record
TIER_DEFAULTS: dict[TrustTierLevel, dict[str, Any]] = {
    TrustTierLevel.unverified: {
        "max_instance_vcpus": 2,
        "max_gpu_vram_gb": None,  # No GPU allowed — NULL but enforced as 0 below
        "max_gpu_hours_month": 10,
        "max_spend_usd_month": 50.00,
    },
    TrustTierLevel.tier1: {
        "max_instance_vcpus": 8,
        "max_gpu_vram_gb": 8,
        "max_gpu_hours_month": 50,
        "max_spend_usd_month": 200.00,
    },
    TrustTierLevel.tier2: {
        "max_instance_vcpus": 32,
        "max_gpu_vram_gb": 48,
        "max_gpu_hours_month": 500,
        "max_spend_usd_month": 2000.00,
    },
    TrustTierLevel.tier3: {
        "max_instance_vcpus": None,  # Unlimited
        "max_gpu_vram_gb": None,
        "max_gpu_hours_month": None,
        "max_spend_usd_month": None,
    },
}


@dataclass
class TrustViolation:
    rule: str
    requested: Any
    allowed: Any
    message: str


class TrustTierViolationError(Exception):
    """Raised when an operation exceeds the user's trust tier limits."""
    def __init__(self, user_id: uuid.UUID, violations: list[TrustViolation]):
        super().__init__(
            f"Trust tier violation for user {user_id}: "
            + "; ".join(v.message for v in violations)
        )
        self.user_id = user_id
        self.violations = violations


def check_instance_launch(
    *,
    user_id: uuid.UUID,
    vcpus: int | None,
    gpu_vram_gb: int | None,
    tier: TrustTierLevel,
    max_instance_vcpus: int | None,
    max_gpu_vram_gb: int | None,
    is_wallet_frozen: bool,
) -> None:
    """
    Validates that the requested instance spec is within the user's trust tier.
    Raises TrustTierViolationError with all violations if any limit is exceeded.

    This is a pure validation function — no DB access, easy to unit test.
    """
    violations: list[TrustViolation] = []

    # Frozen wallet = no new instances, period
    if is_wallet_frozen:
        raise TrustTierViolationError(user_id, [
            TrustViolation(
                rule="wallet_frozen",
                requested="launch_instance",
                allowed=False,
                message="Wallet is frozen — no new instances permitted",
            )
        ])

    # vCPU cap
    if vcpus is not None and max_instance_vcpus is not None:
        if vcpus > max_instance_vcpus:
            violations.append(TrustViolation(
                rule="max_instance_vcpus",
                requested=vcpus,
                allowed=max_instance_vcpus,
                message=f"Requested {vcpus} vCPUs exceeds tier limit of {max_instance_vcpus}",
            ))

    # GPU VRAM cap
    if gpu_vram_gb is not None and gpu_vram_gb > 0:
        if tier == TrustTierLevel.unverified:
            violations.append(TrustViolation(
                rule="gpu_not_allowed_unverified",
                requested=f"{gpu_vram_gb} GB VRAM",
                allowed=0,
                message="GPU access requires phone verification (tier1 or above)",
            ))
        elif max_gpu_vram_gb is not None and gpu_vram_gb > max_gpu_vram_gb:
            violations.append(TrustViolation(
                rule="max_gpu_vram_gb",
                requested=gpu_vram_gb,
                allowed=max_gpu_vram_gb,
                message=f"Requested {gpu_vram_gb} GB GPU VRAM exceeds tier limit of {max_gpu_vram_gb} GB",
            ))

    if violations:
        log.warning(
            "trust_tier.violation",
            user_id=str(user_id),
            tier=tier.value,
            violations=[v.rule for v in violations],
        )
        raise TrustTierViolationError(user_id, violations)

    log.info("trust_tier.ok", user_id=str(user_id), tier=tier.value)


def get_tier_defaults(tier: TrustTierLevel) -> dict[str, Any]:
    """Returns the default caps for the given tier."""
    return TIER_DEFAULTS.get(tier, TIER_DEFAULTS[TrustTierLevel.unverified]).copy()
