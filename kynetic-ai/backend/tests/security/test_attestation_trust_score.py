"""
Unit test suite for Part 5 (TPM 2.0 Host Attestation) and Part 6 (Host Trust Score Engine).
"""

import uuid
import pytest

from host_agent.attestation import TPMAttestationClient
from services.security_service.trust_manager import calculate_host_trust_score


def test_tpm_attestation_quote_generation():
    """Verify TPMAttestationClient generates nonce-embedded signed quotes."""
    host_id = str(uuid.uuid4())
    client = TPMAttestationClient(host_id)
    nonce = "CHALLENGE_NONCE_1234567890ABCDEF"

    quote = client.generate_quote(nonce)
    assert quote["nonce"] == nonce
    assert quote["pcr_digest"] is not None
    assert quote["quote_signature"].startswith("AIK_SIG_")
    assert quote["secure_boot_enabled"] is True
    assert quote["measured_boot_compliant"] is True


def test_host_trust_score_calculation_low_risk():
    """Verify clean attestation + modern software yields 100.0 score (LOW_RISK)."""
    score, band = calculate_host_trust_score(
        attestation_status="current",
        secure_boot_compliant=True,
        measured_boot_compliant=True,
        kernel_version_fresh=True,
        agent_version_fresh=True,
    )
    assert score == 100.0
    assert band == "LOW_RISK"


def test_host_trust_score_hard_gate_on_attestation_failure():
    """Verify Part 6.3 Hard Gate Rule: failed/expired attestation caps score at 29.0 (CRITICAL)."""
    # Even if all other software components are 100% perfect:
    score, band = calculate_host_trust_score(
        attestation_status="failed",
        secure_boot_compliant=True,
        measured_boot_compliant=True,
        kernel_version_fresh=True,
        agent_version_fresh=True,
    )
    assert score <= 29.0
    assert band == "CRITICAL"

    score_expired, band_expired = calculate_host_trust_score(
        attestation_status="expired",
        secure_boot_compliant=True,
        measured_boot_compliant=True,
    )
    assert score_expired <= 29.0
    assert band_expired == "CRITICAL"
