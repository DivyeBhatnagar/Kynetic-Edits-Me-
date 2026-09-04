r"""
Linearly Homomorphic Signature Tensor Verification.
Enables pipeline-parallel and tensor-parallel worker nodes to authenticate and verify
linear combinations and partitions of model weight tensors without requiring full central reconstruction.
"""

import hashlib
import secrets
from dataclasses import dataclass
from typing import Dict, List, Tuple


PRIME_Q = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F


@dataclass
class HomomorphicSignature:
    tag: str
    signature_val: int
    vector_dim: int


class HomomorphicTensorVerifier:
    def __init__(self, key_seed: bytes = b"kynetic_homomorphic_tensor_sig_seed_2026", vector_dim: int = 16):
        self.vector_dim = vector_dim
        self.prime = PRIME_Q

        # Derive evaluation secret vector s \in F_q^d
        self.secret_vector: List[int] = []
        for i in range(vector_dim):
            h = hashlib.sha256(key_seed + i.to_bytes(4, "big")).digest()
            self.secret_vector.append(int.from_bytes(h, "big") % self.prime)

    def sign_tensor_chunk(self, tag: str, tensor_chunk: List[float]) -> HomomorphicSignature:
        r"""
        Computes linearly homomorphic signature:
        \sigma(v) = (Hash(tag) + \sum_{i} s_i \cdot \lfloor v_i \cdot 10^6 \rceil) \pmod p
        """
        tag_hash = int(hashlib.sha256(tag.encode()).hexdigest(), 16) % self.prime
        dot_product = 0

        for i, val in enumerate(tensor_chunk[:self.vector_dim]):
            fixed_point = int(val * 1_000_000) % self.prime
            dot_product = (dot_product + self.secret_vector[i] * fixed_point) % self.prime

        sig = (tag_hash + dot_product) % self.prime
        return HomomorphicSignature(tag=tag, signature_val=sig, vector_dim=self.vector_dim)

    def verify_chunk(self, sig: HomomorphicSignature, tensor_chunk: List[float]) -> bool:
        """Verify single signed tensor chunk."""
        expected_sig = self.sign_tensor_chunk(sig.tag, tensor_chunk)
        return sig.signature_val == expected_sig.signature_val

    def combine_signatures(
        self,
        sigs: List[HomomorphicSignature],
        weights: List[float],
        combined_tag: str,
    ) -> HomomorphicSignature:
        r"""
        Homomorphic property:
        \sigma(\sum w_j v_j) = \sum w_j \sigma(v_j) + Adjustment(Tags) \pmod p
        """
        combined_sig = 0

        for sig, w in zip(sigs, weights):
            w_fixed = int(w * 1_000_000) % self.prime
            combined_sig = (combined_sig + w_fixed * sig.signature_val) % self.prime

        return HomomorphicSignature(
            tag=combined_tag,
            signature_val=combined_sig,
            vector_dim=self.vector_dim,
        )
