"""
Unit test suite for Parts 11 to 16 of Implementation Plan v2:
- Part 12: Container Security Profiles (STANDARD, HARDENED, VERIFIED)
- Part 13: Cosign Sigstore Image Signature Verification
- Part 15 & 16: Runtime Risk Engine & Automated Response Actions (ALLOW -> QUARANTINE)
"""

import pytest

from host_agent.container_profiles import SecurityProfileTier, get_security_profile
from services.security_service.image_scanner import verify_image_signature
from services.security_service.runtime_monitor import calculate_runtime_risk_score


def test_container_security_profile_selection():
    """Verify Part 12 Container Security Profiles (STANDARD & HARDENED)."""
    std = get_security_profile(SecurityProfileTier.STANDARD)
    assert std.read_only_root_fs is False
    assert std.no_new_privileges is True
    assert "SYS_ADMIN" in std.cap_drop

    hardened = get_security_profile(SecurityProfileTier.HARDENED)
    assert hardened.read_only_root_fs is True
    assert hardened.apparmor_profile == "kynetic-hardened"
    assert "ALL" in hardened.cap_drop


def test_cosign_image_signature_verification():
    """Verify Part 13 Cosign signature verification admission gate."""
    valid, msg = verify_image_signature("registry.kynetic.ai/workload/pytorch:latest")
    assert valid is True
    assert "Cosign signature verified" in msg


def test_runtime_risk_score_calculation_bands():
    """Verify Part 16 Composite Runtime Risk Score and response action mapping."""
    # 1. Normal execution -> ALLOW (0–20)
    score_low, band_low, act_low = calculate_runtime_risk_score(customer_risk=0, host_risk=0)
    assert score_low < 20.0
    assert band_low == "Normal"
    assert act_low == "ALLOW"

    # 2. Suspicious Falco alerts -> RESTRICT (40–60)
    score_mid, band_mid, act_mid = calculate_runtime_risk_score(
        falco_alert_count=5,
        network_violations_count=8,
    )
    assert 40.0 <= score_mid < 60.0
    assert band_mid == "Concerning"
    assert act_mid == "RESTRICT"

    # 3. Mining suspected + CVEs -> QUARANTINE (80–100)
    score_high, band_high, act_high = calculate_runtime_risk_score(
        mining_suspected=True,
        falco_alert_count=6,
        image_cve_critical_count=3,
    )
    assert score_high >= 80.0
    assert band_high == "Severe"
    assert act_high == "QUARANTINE"
