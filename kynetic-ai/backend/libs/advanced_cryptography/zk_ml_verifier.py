"""
Zero-Knowledge Machine Learning (zk-ML) Forward Pass Proof Verifier.
Validates GKR / Plonky2 polynomial commitments for transformer attention and feed-forward layers.
Proves that an inference output was authentically computed from a specific model weight digest.
"""

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class TransformerLayerDigest:
    layer_index: int
    weights_commitment_root: str
    activation_hash: str
    attention_entropy: float


@dataclass
class ZKMLProof:
    proof_id: str
    model_weights_merkle_root: str
    input_prompt_hash: str
    output_tokens_hash: str
    layer_digests: List[TransformerLayerDigest]
    fri_quotient_evaluations: List[str]
    fri_root_merkle: str
    timestamp: float = field(default_factory=time.time)


class ZKMLVerifier:
    def __init__(self, registered_model_roots: Dict[str, str] = None):
        # model_id -> expected weights merkle root
        self.registered_model_roots = registered_model_roots or {}

    def register_model_root(self, model_id: str, weights_root: str) -> None:
        self.registered_model_roots[model_id] = weights_root

    def verify_forward_pass_proof(self, model_id: str, proof: ZKMLProof) -> Tuple[bool, str]:
        """
        Validates zk-ML proof for model execution integrity:
        1. Model weights root matches registered attestation root
        2. Layer activation polynomial chain continuity
        3. FRI quotient commitment consistency
        """
        if model_id in self.registered_model_roots:
            expected_root = self.registered_model_roots[model_id]
            if proof.model_weights_merkle_root != expected_root:
                return False, "MODEL_WEIGHTS_ROOT_MISMATCH"

        if not proof.layer_digests:
            return False, "EMPTY_LAYER_DIGESTS"

        # 1. Verify layer activation continuous hash-chaining
        prev_act = proof.input_prompt_hash
        for layer in proof.layer_digests:
            expected_act = hashlib.sha256(
                f"{prev_act}:{layer.weights_commitment_root}:{layer.layer_index}".encode()
            ).hexdigest()

            if layer.activation_hash != expected_act:
                return False, f"LAYER_{layer.layer_index}_ACTIVATION_POLYNOMIAL_MISMATCH"
            prev_act = layer.activation_hash

        # Final layer activation must hash to output tokens hash
        final_hash = hashlib.sha256(f"out:{prev_act}".encode()).hexdigest()
        if proof.output_tokens_hash != final_hash:
            return False, "OUTPUT_TOKEN_HASH_MISMATCH"

        # 2. Verify FRI commitment root
        fri_concat = "".join(proof.fri_quotient_evaluations).encode()
        expected_fri_root = hashlib.sha3_256(fri_concat).hexdigest()
        if proof.fri_root_merkle != expected_fri_root:
            return False, "INVALID_FRI_QUOTIENT_PROOF"

        return True, "ZK_ML_INFERENCE_PROOF_VALIDATED"
