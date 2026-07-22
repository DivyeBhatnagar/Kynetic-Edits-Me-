"""
Tests — Trust Tier Enforcement.

Validates the pure check_instance_launch() function against
all tier levels and violation combinations.
"""

import os
import uuid

import pytest

os.environ.setdefault("SCANNER_MOCK", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key")
os.environ.setdefault("ADMIN_JWT_SECRET_KEY", "test_admin_secret")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("PROVISIONING_SERVICE_URL", "http://localhost:8005")
os.environ.setdefault("WALLET_BILLING_SERVICE_URL", "http://localhost:8004")
os.environ.setdefault("HOST_SERVICE_URL", "http://localhost:8002")


from libs.db_models.security_models import TrustTierLevel
from services.security_service.trust_tier import (
    TIER_DEFAULTS,
    TrustTierViolationError,
    TrustViolation,
    check_instance_launch,
    get_tier_defaults,
)

USER = uuid.uuid4()


# ── Helper ─────────────────────────────────────────────────────────────────

def check(
    tier: TrustTierLevel,
    vcpus: int | None = 1,
    gpu_vram_gb: int | None = None,
    is_wallet_frozen: bool = False,
) -> None:
    defaults = get_tier_defaults(tier)
    check_instance_launch(
        user_id=USER,
        vcpus=vcpus,
        gpu_vram_gb=gpu_vram_gb,
        tier=tier,
        max_instance_vcpus=defaults["max_instance_vcpus"],
        max_gpu_vram_gb=defaults["max_gpu_vram_gb"],
        is_wallet_frozen=is_wallet_frozen,
    )


# ── Frozen wallet ──────────────────────────────────────────────────────────

def test_frozen_wallet_blocks_all():
    """Frozen wallet → no new instances regardless of tier."""
    with pytest.raises(TrustTierViolationError) as exc:
        check(TrustTierLevel.tier3, vcpus=1, is_wallet_frozen=True)
    assert any(v.rule == "wallet_frozen" for v in exc.value.violations)


# ── Unverified tier ────────────────────────────────────────────────────────

def test_unverified_cpu_within_limits():
    """Unverified user with 2 vCPUs and no GPU → allowed."""
    check(TrustTierLevel.unverified, vcpus=2, gpu_vram_gb=None)  # No exception


def test_unverified_too_many_vcpus():
    """Unverified user requesting 4 vCPUs (limit=2) → violation."""
    with pytest.raises(TrustTierViolationError) as exc:
        check(TrustTierLevel.unverified, vcpus=4)
    assert any(v.rule == "max_instance_vcpus" for v in exc.value.violations)
    assert exc.value.violations[0].allowed == 2


def test_unverified_gpu_blocked():
    """Unverified users cannot access any GPU."""
    with pytest.raises(TrustTierViolationError) as exc:
        check(TrustTierLevel.unverified, vcpus=1, gpu_vram_gb=8)
    assert any(v.rule == "gpu_not_allowed_unverified" for v in exc.value.violations)


# ── Tier 1 ─────────────────────────────────────────────────────────────────

def test_tier1_gpu_within_limits():
    """Phone-verified user with 8 GB VRAM → allowed."""
    check(TrustTierLevel.tier1, vcpus=4, gpu_vram_gb=8)  # No exception


def test_tier1_gpu_exceeds_limit():
    """Tier1 user requesting 16 GB VRAM (limit=8) → violation."""
    with pytest.raises(TrustTierViolationError) as exc:
        check(TrustTierLevel.tier1, vcpus=4, gpu_vram_gb=16)
    assert any(v.rule == "max_gpu_vram_gb" for v in exc.value.violations)


def test_tier1_vcpu_within_limits():
    """Tier1 can use up to 8 vCPUs."""
    check(TrustTierLevel.tier1, vcpus=8)  # No exception


def test_tier1_vcpu_exceeds():
    """Tier1 requesting 9 vCPUs (limit=8) → violation."""
    with pytest.raises(TrustTierViolationError):
        check(TrustTierLevel.tier1, vcpus=9)


# ── Tier 2 ─────────────────────────────────────────────────────────────────

def test_tier2_high_end_gpu():
    """ID-verified user with 48 GB VRAM → allowed."""
    check(TrustTierLevel.tier2, vcpus=16, gpu_vram_gb=48)  # No exception


def test_tier2_gpu_exceeds_limit():
    """Tier2 cannot exceed 48 GB VRAM."""
    with pytest.raises(TrustTierViolationError) as exc:
        check(TrustTierLevel.tier2, vcpus=16, gpu_vram_gb=80)
    assert any(v.rule == "max_gpu_vram_gb" for v in exc.value.violations)


# ── Tier 3 ─────────────────────────────────────────────────────────────────

def test_tier3_no_caps():
    """Enterprise tier has NULL caps — all requests allowed."""
    defaults = TIER_DEFAULTS[TrustTierLevel.tier3]
    assert defaults["max_instance_vcpus"] is None
    assert defaults["max_gpu_vram_gb"] is None
    # With NULL caps, check should not raise
    check_instance_launch(
        user_id=USER,
        vcpus=256,
        gpu_vram_gb=640,
        tier=TrustTierLevel.tier3,
        max_instance_vcpus=None,   # NULL = no cap
        max_gpu_vram_gb=None,      # NULL = no cap
        is_wallet_frozen=False,
    )


# ── Multiple violations ────────────────────────────────────────────────────

def test_multiple_violations_collected():
    """Both vCPU and GPU violations are collected and reported together."""
    with pytest.raises(TrustTierViolationError) as exc:
        check(TrustTierLevel.tier1, vcpus=10, gpu_vram_gb=16)
    rules = [v.rule for v in exc.value.violations]
    assert "max_instance_vcpus" in rules
    assert "max_gpu_vram_gb" in rules


# ── TIER_DEFAULTS completeness ─────────────────────────────────────────────

def test_tier_defaults_complete():
    """Every TrustTierLevel must have a TIER_DEFAULTS entry."""
    for level in TrustTierLevel:
        assert level in TIER_DEFAULTS, f"Missing TIER_DEFAULTS entry for {level}"


def test_tier_defaults_tier3_all_none():
    """Tier3 should have all None caps."""
    t3 = TIER_DEFAULTS[TrustTierLevel.tier3]
    for key, value in t3.items():
        assert value is None, f"Tier3.{key} should be None (unlimited), got {value}"
