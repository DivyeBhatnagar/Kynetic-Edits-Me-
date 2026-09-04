"""
Unit tests for Plan v16: Post-Quantum Double-Ratchet, TFHE Bootstrap Guard, zk-ML Verifier,
Ring Signature Dispatcher, Weight Steganography Scanner, and LoRA Spectral Filter.
"""

import hashlib
import os
import struct
import pytest

from backend.libs.advanced_cryptography.pq_double_ratchet import (
    PQDoubleRatchetSession, PQRatchetMessage
)
from backend.libs.advanced_cryptography.tfhe_bootstrap_guard import (
    TFHEBootstrapGuard, CiphertextNoiseBudget
)
from backend.libs.advanced_cryptography.zk_ml_verifier import (
    ZKMLVerifier, ZKMLProof, TransformerLayerDigest
)
from backend.libs.advanced_cryptography.ring_signature_dispatcher import (
    RingSignatureDispatcher, LinkableRingSignature
)
from backend.libs.model_security.weight_steganography_scanner import (
    WeightSteganographyScanner, SteganographyScanReport
)
from backend.libs.model_security.lora_spectral_filter import (
    LoRASpectralFilter, LoRASpectralReport
)


# 1. Post-Quantum Double Ratchet
def test_pq_double_ratchet_full_conversation():
    shared_master_seed = os.urandom(32)

    alice = PQDoubleRatchetSession(shared_master_root_key=shared_master_seed, is_initiator=True)
    bob = PQDoubleRatchetSession(shared_master_root_key=shared_master_seed, is_initiator=False)

    # Alice sends to Bob
    msg1 = alice.encrypt_message(b"Confidential Model Schedule Task #101")
    ok, plaintext1, err1 = bob.decrypt_message(msg1)
    assert ok is True
    assert plaintext1 == b"Confidential Model Schedule Task #101"

    # Bob replies to Alice
    msg2 = bob.encrypt_message(b"Acknowledged Task #101 with Enclave Quorum")
    ok, plaintext2, err2 = alice.decrypt_message(msg2)
    assert ok is True
    assert plaintext2 == b"Acknowledged Task #101 with Enclave Quorum"

    # Alice sends another message (ratchet advances)
    msg3 = alice.encrypt_message(b"Deploying secure microVM")
    ok, plaintext3, err3 = bob.decrypt_message(msg3)
    assert ok is True
    assert plaintext3 == b"Deploying secure microVM"


# 2. TFHE Bootstrap Guard
def test_tfhe_bootstrap_guard():
    guard = TFHEBootstrapGuard(bootstrap_threshold_ratio=0.50)
    guard.register_ciphertext("ct_a")
    guard.register_ciphertext("ct_b")

    # Perform multiple multiplications until noise budget requires bootstrap
    needs_bs, res = guard.record_homomorphic_multiplication("ct_a", "ct_b", "ct_res_1")
    assert "ct_res_1" in guard.tracked_ciphertexts
    assert res.multiplication_depth == 1
    old_noise = res.current_noise_var

    # Execute bootstrapping circuit
    ok, new_noise, msg = guard.execute_bootstrapping_circuit("ct_res_1")
    assert ok is True
    assert "BOOTSTRAPPING_REFRESH_SUCCESSFUL" in msg
    assert new_noise < old_noise


# 3. zk-ML Verifier
def test_zk_ml_verifier():
    verifier = ZKMLVerifier()
    model_root = "0xdeadbeef_model_weights_merkle_root_v1"
    verifier.register_model_root("transformer_llama3_70b", model_root)

    prompt_hash = hashlib.sha256(b"What is quantum computing?").hexdigest()

    # Build layer chain
    l0_act = hashlib.sha256(f"{prompt_hash}:weights_l0:0".encode()).hexdigest()
    l1_act = hashlib.sha256(f"{l0_act}:weights_l1:1".encode()).hexdigest()
    out_tokens_hash = hashlib.sha256(f"out:{l1_act}".encode()).hexdigest()

    layers = [
        TransformerLayerDigest(layer_index=0, weights_commitment_root="weights_l0", activation_hash=l0_act, attention_entropy=4.2),
        TransformerLayerDigest(layer_index=1, weights_commitment_root="weights_l1", activation_hash=l1_act, attention_entropy=3.9),
    ]

    fri_evals = ["fri_poly_eval_0", "fri_poly_eval_1"]
    fri_root = hashlib.sha3_256("".join(fri_evals).encode()).hexdigest()

    proof = ZKMLProof(
        proof_id="proof_zkml_998",
        model_weights_merkle_root=model_root,
        input_prompt_hash=prompt_hash,
        output_tokens_hash=out_tokens_hash,
        layer_digests=layers,
        fri_quotient_evaluations=fri_evals,
        fri_root_merkle=fri_root,
    )

    valid, reason = verifier.verify_forward_pass_proof("transformer_llama3_70b", proof)
    assert valid is True
    assert reason == "ZK_ML_INFERENCE_PROOF_VALIDATED"


# 4. Ring Signature Dispatcher
def test_ring_signature_dispatcher():
    dispatcher = RingSignatureDispatcher()

    # Create ring of 5 public keys
    priv_keys = [12345, 67890, 11223, 44556, 77889]
    pub_keys = [pow(dispatcher.g, k, dispatcher.p) for k in priv_keys]

    signer_idx = 2
    signer_priv = priv_keys[signer_idx]
    message = "AUTHORIZE_GPU_DISPATCH_JOB_ID_7781"

    sig = dispatcher.generate_ring_signature(message, pub_keys, signer_idx, signer_priv)
    ok, msg = dispatcher.verify_ring_signature(sig, message)
    assert ok is True
    assert "RING_SIGNATURE_AUTHENTICATED_ANONYMOUSLY" in msg

    # Replay protection on key image
    ok_replay, err = dispatcher.verify_ring_signature(sig, message)
    assert ok_replay is False
    assert "KEY_IMAGE_ALREADY_SPENT" in err


# 5. Model Weight Steganography Scanner
def test_weight_steganography_scanner():
    scanner = WeightSteganographyScanner()

    # Normal clean weights
    clean_weights = [0.123456, -0.987654, 0.554433, 1.234567] * 32
    clean_rep = scanner.scan_tensor_weights("clean_layer.weight", clean_weights)
    assert clean_rep.hidden_payload_detected is False

    # Steganographically injected shellcode
    # Inject \x7fELF in LSBs
    shellcode = b"\x7fELF" + os.urandom(12)
    injected_weights = []
    for byte in shellcode:
        for bit_idx in range(7, -1, -1):
            bit = (byte >> bit_idx) & 1
            # Craft float with matching LSB
            packed = struct.pack(">f", 1.0)
            int_val = (struct.unpack(">I", packed)[0] & ~1) | bit
            injected_weights.append(struct.unpack(">f", struct.pack(">I", int_val))[0])

    poison_rep = scanner.scan_tensor_weights("backdoor_layer.weight", injected_weights)
    assert poison_rep.hidden_payload_detected is True
    assert "COVERT_EXECUTABLE_MAGIC_FOUND" in poison_rep.threat_details


# 6. LoRA Spectral Filter
def test_lora_spectral_filter():
    filter_engine = LoRASpectralFilter()

    # Normal clean low-rank matrices (uniform small variance)
    r = 4
    d_in, d_out = 8, 8
    clean_a = [[0.01 * (i + j) for j in range(d_in)] for i in range(r)]
    clean_b = [[0.01 * (i - j) for j in range(r)] for i in range(d_out)]

    clean_report = filter_engine.analyze_adapter("lora_clean_v1", clean_a, clean_b)
    assert clean_report.is_backdoor_suspected is False
    assert clean_report.status == "LORA_SPECTRAL_PROFILE_CLEAN"
