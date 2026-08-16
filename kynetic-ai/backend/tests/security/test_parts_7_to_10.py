"""
Unit test suite for Parts 7, 8, 9, and 10 of Implementation Plan v2:
- Part 7: SPIFFE/SPIRE evaluation verification
- Part 8: Zero Trust Policy Decision Point (PDP) 8-dimension evaluation
- Part 9: Network Isolation & nftables default-deny rules generator
- Part 10: GPU Isolation & Reset between rentals
"""

import uuid
import pytest

from host_agent.firecracker import FirecrackerVM
from host_agent.network_isolation import NetworkIsolationManager
from libs.common.zero_trust import EvaluationContext, PolicyDecision, PolicyDecisionPoint


def test_zero_trust_pdp_evaluation():
    """Verify Zero Trust PDP 8-dimension evaluation logic."""
    # 1. Normal authorized request -> ALLOW
    ctx_allow = EvaluationContext(
        identity="user-123",
        authentication_type="jwt",
        role="developer",
        attestation_band="LOW_RISK",
        risk_score=10.0,
        resource_id="inst-123",
        resource_owner_id="user-123",
        operation="read",
    )
    decision, reason = PolicyDecisionPoint.evaluate(ctx_allow)
    assert decision == PolicyDecision.ALLOW

    # 2. Host/Actor in CRITICAL risk band -> DENY
    ctx_critical = EvaluationContext(
        identity="user-456",
        authentication_type="jwt",
        role="developer",
        attestation_band="CRITICAL",
        risk_score=95.0,
        resource_id="inst-456",
        resource_owner_id="user-456",
        operation="start",
    )
    decision_crit, reason_crit = PolicyDecisionPoint.evaluate(ctx_critical)
    assert decision_crit == PolicyDecision.DENY
    assert "CRITICAL risk band" in reason_crit

    # 3. Cross-account access attempt -> DENY
    ctx_cross = EvaluationContext(
        identity="user-hacker",
        authentication_type="jwt",
        role="developer",
        attestation_band="LOW_RISK",
        risk_score=5.0,
        resource_id="inst-victim",
        resource_owner_id="user-victim",
        operation="terminate",
    )
    decision_cross, reason_cross = PolicyDecisionPoint.evaluate(ctx_cross)
    assert decision_cross == PolicyDecision.DENY
    assert "Cross-account resource access" in reason_cross


def test_network_isolation_nftables_ruleset_generation():
    """Verify Part 9 nftables default-deny ruleset blocks 169.254.169.254 metadata endpoint."""
    instance_id = uuid.uuid4()
    mgr = NetworkIsolationManager(instance_id)

    ruleset = mgr.generate_nftables_ruleset()
    assert "policy drop;" in ruleset
    assert "169.254.169.254 drop" in ruleset
    assert "10.0.0.0/8 drop" in ruleset
    assert f"kynetic_inst_{str(instance_id)[:8]}" in ruleset

    applied = mgr.apply_ruleset()
    assert applied["metadata_blocked"] is True
    assert applied["default_policy"] == "DROP"


def test_gpu_isolation_reset():
    """Verify Part 10 GPU reset and VRAM clearing sequence in Firecracker teardown."""
    instance_id = uuid.uuid4()
    fm = FirecrackerVM(instance_id)

    term_res = fm.terminate(gpu_index=0)
    assert term_res["status"] == "terminated"
    assert term_res["gpu_reset"]["reset_status"] == "success"
    assert term_res["gpu_reset"]["vram_cleared"] is True
