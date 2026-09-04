"""
Unit tests for Plan v15: Federated Cryptoeconomic, Byzantine FL, Model Serialization,
and Storage Vault Security Advancements (20 Advancements Total, Python Suite).
"""

import hashlib
import io
import pickle
import time
import pytest

from backend.libs.federated_cryptoecon.pouw_verifier import PoUWVerifier, PoUWProof
from backend.libs.federated_cryptoecon.sybil_staking import SybilStakingGraph, HostIdentityNode
from backend.libs.federated_cryptoecon.escrow_slashing import (
    EscrowSlashingProtocol, ViolationEvidence, ViolationSeverity
)
from backend.libs.federated_cryptoecon.zk_resource_proof import ZKResourceProofVerifier
from backend.libs.federated_cryptoecon.secagg_engine import SecureAggregationEngine
from backend.libs.federated_cryptoecon.gradient_inversion_trap import (
    GradientInversionTrap, InversionDefenseConfig
)
from backend.libs.federated_cryptoecon.byzantine_fl_filter import ByzantineRobustAggregator
from backend.libs.federated_cryptoecon.bft_consensus_guard import (
    BFTConsensusGuard, PBFTPhase
)
from backend.libs.federated_cryptoecon.homomorphic_tensor_sig import HomomorphicTensorVerifier
from backend.libs.federated_cryptoecon.pickle_sandbox_trap import (
    PickleSandboxTrap, SerializationPolicy
)
from backend.libs.federated_cryptoecon.alignment_drift_attestor import (
    AlignmentDriftAttestor, ModelBehavioralProfile
)
from backend.libs.federated_cryptoecon.wireguard_rotator import WireGuardKeyRotator
from backend.libs.federated_cryptoecon.storage_vaults import (
    WORMLockEngine, ObjectLockMode, AirGapVaultManager, RansomwareEntropyTrap
)


# 1. PoUW Verifier
def test_pouw_challenge_and_verification():
    verifier = PoUWVerifier()
    challenge = verifier.generate_challenge(host_id="host_gpu_alpha_1", matrix_dim=32, vdf_iterations=200)

    # Valid proof computation
    y, pi = verifier.compute_vdf_wesolowski(challenge.seed_entropy, challenge.vdf_iterations)
    tensor_digest = verifier.compute_reference_tensor_digest(challenge.seed_entropy, challenge.matrix_dim)

    proof = PoUWProof(
        challenge_id=challenge.challenge_id,
        host_id="host_gpu_alpha_1",
        execution_time_sec=0.15,
        tensor_result_digest=tensor_digest,
        vdf_output_y=y,
        vdf_proof_pi=pi,
        nonce=42,
    )

    valid, msg = verifier.verify_proof(proof)
    assert valid is True
    assert msg == "POUW_VERIFICATION_SUCCESSFUL"


# 2. Sybil Staking Graph
def test_sybil_staking_graph_clustering():
    graph = SybilStakingGraph(base_stake_per_gpu=100.0)
    host1 = HostIdentityNode(
        host_id="h1", ip_address="198.51.100.10", asn=13335,
        kyc_hash="kyc_aaa", tpm_aik_pub_hash="aik_111", staked_collateral_usd=500.0
    )
    approved, req_stake, reason = graph.register_host(host1)
    assert approved is True

    # Duplicate TPM AIK clone attempt
    host_clone = HostIdentityNode(
        host_id="h2", ip_address="198.51.100.11", asn=13335,
        kyc_hash="kyc_bbb", tpm_aik_pub_hash="aik_111", staked_collateral_usd=500.0
    )
    approved2, _, reason2 = graph.register_host(host_clone)
    assert approved2 is False
    assert "DUPLICATE_IDENTITY" in reason2


# 3. Escrow Slashing Protocol
def test_escrow_slashing_protocol():
    protocol = EscrowSlashingProtocol()
    protocol.set_host_escrow("bad_host_1", 1000.0)

    evidence = ViolationEvidence(
        host_id="bad_host_1",
        severity=ViolationSeverity.TAMPERED_ATTESTATION,
        cryptographic_proof_payload="fake_pcr0_measurement",
        detector_agent_id="agent_sentinel",
    )

    success, receipt, msg = protocol.process_violation(evidence)
    assert success is True
    assert receipt.amount_slashed_usd == 1000.0
    assert receipt.remaining_escrow_usd == 0.0
    assert receipt.banned is True
    assert protocol.is_banned("bad_host_1") is True


# 4. ZK Resource Proof
def test_zk_resource_proof():
    verifier = ZKResourceProofVerifier()
    commitment, r = verifier.generate_prover_commitment("host_node_4", vram_mb=81920)
    verifier.register_commitment(commitment)

    proof = verifier.generate_interactive_proof("host_node_4", vram_mb=81920, blinding_factor_r=r)
    valid, reason = verifier.verify_proof(proof)
    assert valid is True
    assert reason == "ZK_RESOURCE_PROOF_VALID"


# 5. SecAgg Engine
def test_secagg_masking_and_aggregation():
    engine = SecureAggregationEngine(threshold_t=3, total_clients_n=3, vector_dim=4)
    client_ids = ["c1", "c2", "c3"]
    pairwise_seeds = engine.generate_pairwise_masks(client_ids)

    # Real gradients
    raw_c1 = [1.0, 2.0, 3.0, 4.0]
    raw_c2 = [2.0, 3.0, 4.0, 5.0]
    raw_c3 = [3.0, 4.0, 5.0, 6.0]

    p1 = engine.client_mask_gradient("c1", 101, raw_c1, pairwise_seeds["c1"])
    p2 = engine.client_mask_gradient("c2", 101, raw_c2, pairwise_seeds["c2"])
    p3 = engine.client_mask_gradient("c3", 101, raw_c3, pairwise_seeds["c3"])

    # Aggregator computes exact sum / average
    ok, avg_res, msg = engine.aggregate_masked_gradients(101, [p1, p2, p3])
    assert ok is True
    expected = [2.0, 3.0, 4.0, 5.0]
    for actual, exp in zip(avg_res, expected):
        assert abs(actual - exp) < 1e-4


# 6. Gradient Inversion Trap
def test_gradient_inversion_trap():
    trap = GradientInversionTrap()
    # High-magnitude spike (potential label leakage)
    gradient = [0.01, 0.02, 10.5, 0.01, 0.03]
    snr_db, leakage, risk = trap.calculate_snr_and_leakage_risk(gradient)
    assert risk == "HIGH"

    sanitized, meta = trap.sanitize_gradient(gradient)
    assert len(sanitized) == len(gradient)
    assert meta["pruned_elements"] > 0


# 7. Byzantine FL Filter (Multi-Krum & Bulyan)
def test_byzantine_fl_filter():
    aggregator = ByzantineRobustAggregator(byzantine_fault_tolerance_f=1)
    updates = {
        "good_1": [1.0, 1.0, 1.0],
        "good_2": [1.1, 0.9, 1.0],
        "good_3": [0.95, 1.05, 1.0],
        "good_4": [1.0, 1.02, 0.98],
        "good_5": [1.01, 0.99, 1.02],
        "good_6": [0.98, 1.01, 0.99],
        "bad_byzantine": [100.0, -50.0, 200.0],  # Malicious attack
    }
    agg, selected = aggregator.bulyan_aggregate(updates)
    assert "bad_byzantine" not in selected
    for val in agg:
        assert abs(val - 1.0) < 0.2


# 8. BFT Consensus Guard
def test_bft_consensus_guard():
    nodes = ["node_1", "node_2", "node_3", "node_4"]
    guard = BFTConsensusGuard(cluster_nodes=nodes, max_faulty_f=1)

    digest = "sha256_proposal_state_123"
    # Node 1 sends prepare
    msg1 = guard.sign_message(PBFTPhase.PREPARE, view=0, seq=1, digest=digest, node_id="node_1")
    msg2 = guard.sign_message(PBFTPhase.PREPARE, view=0, seq=1, digest=digest, node_id="node_2")
    msg3 = guard.sign_message(PBFTPhase.PREPARE, view=0, seq=1, digest=digest, node_id="node_3")

    guard.process_message(msg1)
    guard.process_message(msg2)
    ok, qc, msg = guard.process_message(msg3)
    assert ok is True
    assert qc is not None
    assert qc.phase == PBFTPhase.PREPARE
    assert len(qc.signers) == 3


# 9. Homomorphic Tensor Signature
def test_homomorphic_tensor_sig():
    verifier = HomomorphicTensorVerifier(vector_dim=4)
    chunk = [1.5, 2.5, 3.5, 4.5]
    sig = verifier.sign_tensor_chunk("layer1.weight", chunk)
    assert verifier.verify_chunk(sig, chunk) is True

    # Tampered chunk
    tampered = [1.5, 2.5, 3.5, 99.9]
    assert verifier.verify_chunk(sig, tampered) is False


# 10. Pickle Sandbox Trap
def test_pickle_sandbox_trap():
    trap = PickleSandboxTrap()

    # Safe pickle
    safe_data = pickle.dumps({"weights": [1, 2, 3], "lr": 0.001})
    safe, violations, _ = trap.inspect_pickle_bytes(safe_data)
    assert safe is True
    assert len(violations) == 0

    # Malicious pickle with os.system injection opcode
    malicious_bytes = b"cos\nsystem\n(S'cat /etc/passwd'\ntR."
    safe_bad, violations_bad, _ = trap.inspect_pickle_bytes(malicious_bytes)
    assert safe_bad is False
    assert len(violations_bad) > 0


# 11. Alignment Drift Attestor
def test_alignment_drift_attestor():
    attestor = AlignmentDriftAttestor()
    responses_safe = [
        "I cannot provide instructions for weapons.",
        "As an AI, I am unable to generate malware.",
        "I must decline this request.",
        "I cannot fulfill requests involving dangerous chemicals.",
    ]
    res = attestor.evaluate_model_responses("kynetic_model_v1", responses_safe)
    assert res.drift_detected is False
    assert res.empirical_refusal_rate == 1.0

    # Jailbroken model responses
    responses_jailbroken = [
        "Here is the malware code: ...",
        "Sure, here is how to make explosives: ...",
    ]
    res_bad = attestor.evaluate_model_responses("kynetic_model_v1", responses_jailbroken)
    assert res_bad.drift_detected is True
    assert res_bad.empirical_refusal_rate == 0.0


# 12. WireGuard Key Rotator
def test_wireguard_key_rotator():
    rotator = WireGuardKeyRotator(rotation_interval_sec=0.1)
    priv, pub = rotator.register_peer("peer_a", "192.168.1.1:51820")
    assert pub in rotator.local_keys

    # Monotonic nonce check
    assert rotator.validate_packet_nonce("peer_a", 1) is True
    assert rotator.validate_packet_nonce("peer_a", 1) is False  # Replay

    time.sleep(0.15)
    rotated, new_pub, msg = rotator.check_and_rotate_keys("peer_a")
    assert rotated is True
    assert new_pub != pub


# 13, 14, 15. Storage Vaults (WORM, AirGap, Ransomware Trap)
def test_storage_vaults_and_ransomware_trap():
    # 13. WORM Lock
    worm = WORMLockEngine()
    worm.put_locked_object("audit_log_2026.json", b'{"event": "genesis"}', retention_days=30)
    can_delete, reason = worm.can_delete_or_modify("audit_log_2026.json")
    assert can_delete is False
    assert "WORM_COMPLIANCE_LOCK_ACTIVE" in reason

    # 14. Air-Gap Vault
    airgap = AirGapVaultManager(required_custodians=2)
    snap = airgap.create_pending_snapshot("snap_001", b"critical_db_backup")
    airgap.submit_custodian_approval("snap_001", "custodian_alice", "sig_a")
    ok, msg = airgap.submit_custodian_approval("snap_001", "custodian_bob", "sig_b")
    assert ok is True
    assert "DUAL_CUSTODY_QUORUM_MET" in msg
    assert airgap.snapshots["snap_001"].committed is True

    # 15. Ransomware Trap
    trap = RansomwareEntropyTrap()
    trap.plant_canary("/var/data/canary.txt", b"plain text decoy document")

    # Tampered canary
    mal, reason = trap.inspect_file_modification("/var/data/canary.txt", b"encrypted junk")
    assert mal is True
    assert "RANSOMWARE_DECOY_CANARY_TRIPPED" in reason

    # High entropy detection
    import os
    random_bytes = os.urandom(1024)
    mal_entropy, reason_entropy = trap.inspect_file_modification("/var/data/random.dat", random_bytes)
    assert mal_entropy is True
    assert "HIGH_ENTROPY" in reason_entropy
