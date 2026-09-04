"""
Ephemeral Ring-Signature Anonymous Compute Dispatcher.
Implements Linkable Spontaneous Anonymous Group (LSAG) ring signatures.
Grants anonymous compute execution authorization among a public key ring without linking developer identities.
"""

import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


PRIME = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
G_BASE = 2


@dataclass
class LinkableRingSignature:
    ring_public_keys: List[int]
    key_image: int             # I = x * HashToPoint(P) to prevent double-spending
    challenge_c0: int
    responses_s: List[int]     # One response scalar s_i per ring member
    message_digest: str
    timestamp: float = field(default_factory=time.time)


class RingSignatureDispatcher:
    def __init__(self, p: int = PRIME, g: int = G_BASE):
        self.p = p
        self.g = g
        self.spent_key_images: Set[int] = set()

    def _hash_to_point(self, pub_key: int) -> int:
        """Deterministic mapping from public key to a group element."""
        h_bytes = hashlib.sha256(pub_key.to_bytes(32, "big")).digest()
        return int.from_bytes(h_bytes, "big") % self.p

    def generate_ring_signature(
        self,
        message: str,
        ring_pub_keys: List[int],
        signer_index: int,
        signer_priv_key: int,
    ) -> LinkableRingSignature:
        """
        Generates an LSAG ring signature for the given message.
        Signer proves they own ONE of the private keys in ring_pub_keys without revealing which one.
        """
        n = len(ring_pub_keys)
        msg_hash = hashlib.sha256(message.encode()).hexdigest()
        p_pi = ring_pub_keys[signer_index]
        h_p = self._hash_to_point(p_pi)

        # Key Image I = x * H(P)
        key_image = pow(h_p, signer_priv_key, self.p)

        # 1. Random commitment alpha
        alpha = secrets.randbelow(self.p - 1) + 1
        l_pi = pow(self.g, alpha, self.p)
        r_pi = pow(h_p, alpha, self.p)

        # 2. Challenge loop for ring members
        c = [0] * n
        s = [0] * n

        # Next ring index challenge
        idx = (signer_index + 1) % n
        chal_input = f"{msg_hash}:{l_pi}:{r_pi}:{idx}".encode()
        c[idx] = int(hashlib.sha256(chal_input).hexdigest(), 16) % (self.p - 1)

        for _ in range(n - 1):
            s[idx] = secrets.randbelow(self.p - 1) + 1
            l_idx = (pow(self.g, s[idx], self.p) * pow(ring_pub_keys[idx], c[idx], self.p)) % self.p
            h_idx = self._hash_to_point(ring_pub_keys[idx])
            r_idx = (pow(h_idx, s[idx], self.p) * pow(key_image, c[idx], self.p)) % self.p

            next_idx = (idx + 1) % n
            chal_input = f"{msg_hash}:{l_idx}:{r_idx}:{next_idx}".encode()
            c[next_idx] = int(hashlib.sha256(chal_input).hexdigest(), 16) % (self.p - 1)
            idx = next_idx

        # 3. Close the ring for the actual signer
        s[signer_index] = (alpha - c[signer_index] * signer_priv_key) % (self.p - 1)

        return LinkableRingSignature(
            ring_public_keys=ring_pub_keys,
            key_image=key_image,
            challenge_c0=c[0],
            responses_s=s,
            message_digest=msg_hash,
        )

    def verify_ring_signature(self, sig: LinkableRingSignature, expected_message: str) -> Tuple[bool, str]:
        """
        Verifies LSAG ring signature validity and rejects replayed / double-spent key images.
        """
        # 1. Check double-spend / replay on key image
        if sig.key_image in self.spent_key_images:
            return False, "KEY_IMAGE_ALREADY_SPENT_DOUBLE_DISPATCH_BLOCKED"

        n = len(sig.ring_public_keys)
        if len(sig.responses_s) != n:
            return False, "RING_SIZE_MISMATCH"

        msg_hash = hashlib.sha256(expected_message.encode()).hexdigest()
        if sig.message_digest != msg_hash:
            return False, "MESSAGE_DIGEST_MISMATCH"

        # 2. Recompute ring verification loop starting from c0
        current_c = sig.challenge_c0
        for i in range(n):
            l_i = (pow(self.g, sig.responses_s[i], self.p) * pow(sig.ring_public_keys[i], current_c, self.p)) % self.p
            h_i = self._hash_to_point(sig.ring_public_keys[i])
            r_i = (pow(h_i, sig.responses_s[i], self.p) * pow(sig.key_image, current_c, self.p)) % self.p

            next_idx = (i + 1) % n
            chal_input = f"{msg_hash}:{l_i}:{r_i}:{next_idx}".encode()
            current_c = int(hashlib.sha256(chal_input).hexdigest(), 16) % (self.p - 1)

        # Verification equation: loop must close back to c0
        if current_c != sig.challenge_c0:
            return False, "RING_SIGNATURE_EQUATION_FAILED"

        self.spent_key_images.add(sig.key_image)
        return True, "RING_SIGNATURE_AUTHENTICATED_ANONYMOUSLY"
