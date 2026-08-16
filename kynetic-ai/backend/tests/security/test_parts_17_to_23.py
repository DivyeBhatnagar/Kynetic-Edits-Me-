"""
Unit test suite for Parts 17 to 23 of Implementation Plan v2:
- Part 17: Risk-based Abuse Detection
- Part 18: Kynetic Secret Broker & Scoped Access
- Part 21: Automated Incident Response Pipeline
- Part 22: Verified Compute Scheduling Policy Pre-Filter
"""

import pytest

from libs.common.secret_broker import SecretAccessDeniedError, SecretBroker
from services.marketplace_service.verified_scheduler import filter_verified_compute_hosts
from services.security_service.abuse_detector import AbuseDetector, AbusePatternType
from services.security_service.incident_response import IncidentResponseEngine, IncidentState


def test_abuse_detector_signals():
    """Verify Part 17 Risk-based Abuse Signal collection."""
    report = AbuseDetector.analyze_signals(
        instance_id="inst-1",
        host_id="host-1",
        gpu_hash_rate=8000000.0,
        outbound_connections_per_sec=300,
        unique_external_targets_count=150,
    )
    assert AbusePatternType.CRYPTOMINING in report.detected_patterns
    assert AbusePatternType.PORT_SCANNING in report.detected_patterns
    assert report.risk_score_contribution >= 65.0


def test_secret_broker_scoped_access():
    """Verify Part 18 Secret Broker scoped access enforcement."""
    billing_broker = SecretBroker("wallet_billing_service")
    assert billing_broker.get_secret("payment/stripe_api_key") is not None

    prov_broker = SecretBroker("provisioning_service")
    with pytest.raises(SecretAccessDeniedError):
        prov_broker.get_secret("payment/stripe_api_key")


def test_incident_response_containment():
    """Verify Part 21 automated host containment and workload quarantine."""
    host_inc = IncidentResponseEngine.contain_suspicious_host("host-bad", "Attestation failure")
    assert host_inc.state == IncidentState.CONTAINED
    assert len(host_inc.actions_taken) == 3

    workload_inc = IncidentResponseEngine.contain_suspicious_workload("inst-bad", "Severe risk score")
    assert workload_inc.state == IncidentState.CONTAINED
    assert "nftables zero-egress" in workload_inc.actions_taken[0]


def test_verified_compute_scheduler_filter():
    """Verify Part 22 Verified Compute pre-filter passes only fully compliant hardware."""
    hosts = [
        {
            "id": "host-good",
            "attestation_status": "current",
            "secure_boot_enabled": True,
            "measured_boot_compliant": True,
            "risk_band": "LOW_RISK",
            "storage_encryption": "LUKS2_active",
        },
        {
            "id": "host-bad-attest",
            "attestation_status": "expired",
            "secure_boot_enabled": True,
            "measured_boot_compliant": True,
            "risk_band": "CRITICAL",
            "storage_encryption": "LUKS2_active",
        },
    ]

    eligible = filter_verified_compute_hosts(hosts)
    assert len(eligible) == 1
    assert eligible[0]["id"] == "host-good"
