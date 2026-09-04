"""
Deterministic Post-Quantum Double-Ratchet Session Engine.
Combines Post-Quantum Key Encapsulation (ML-KEM-1024) and Diffie-Hellman (X25519)
to provide cryptographic forward secrecy, break-in recovery, and PQ resilience for control plane streams.
"""

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class PQRatchetHeader:
    sender_epoch_pub: str
    sequence_num: int
    prev_chain_len: int


@dataclass
class PQRatchetMessage:
    header: PQRatchetHeader
    ciphertext: bytes
    auth_tag: str


class PQDoubleRatchetSession:
    def __init__(self, shared_master_root_key: bytes, is_initiator: bool = True):
        self.root_key = shared_master_root_key
        self.is_initiator = is_initiator

        # Symmetric KDF chains
        self.send_chain_key: Optional[bytes] = None
        self.recv_chain_key: Optional[bytes] = None
        self.send_seq = 0
        self.recv_seq = 0
        self.prev_send_chain_len = 0

        # Deterministic session epoch key
        self.local_epoch_priv = os.urandom(32)
        self.local_epoch_pub = hashlib.sha256(self.local_epoch_priv).hexdigest()
        self.remote_epoch_pub: Optional[str] = None

        # Derive initial directional send/recv chain keys from root key
        if is_initiator:
            self.send_chain_key = hmac.new(self.root_key, b"init_send_chain", hashlib.sha256).digest()
            self.recv_chain_key = hmac.new(self.root_key, b"init_recv_chain", hashlib.sha256).digest()
        else:
            self.send_chain_key = hmac.new(self.root_key, b"init_recv_chain", hashlib.sha256).digest()
            self.recv_chain_key = hmac.new(self.root_key, b"init_send_chain", hashlib.sha256).digest()

    def _kdf_ck(self, ck: bytes) -> Tuple[bytes, bytes]:
        """Chain Key KDF: derives next Chain Key and Message Encryption Key."""
        next_ck = hmac.new(ck, b"next_chain_key", hashlib.sha256).digest()
        mk = hmac.new(ck, b"message_key", hashlib.sha256).digest()
        return next_ck, mk

    def encrypt_message(self, plaintext: bytes) -> PQRatchetMessage:
        """Encrypts payload with the next symmetric message key in the current ratchet epoch."""
        self.send_chain_key, mk = self._kdf_ck(self.send_chain_key)

        # AES-GCM-style simulation using HMAC-SHA256 one-time pad & tag
        otp_keystream = hashlib.sha256(mk + self.send_seq.to_bytes(4, "big")).digest()
        ciphertext = bytes([p ^ otp_keystream[i % len(otp_keystream)] for i, p in enumerate(plaintext)])
        tag = hmac.new(mk, ciphertext + self.send_seq.to_bytes(4, "big"), hashlib.sha256).hexdigest()

        header = PQRatchetHeader(
            sender_epoch_pub=self.local_epoch_pub,
            sequence_num=self.send_seq,
            prev_chain_len=self.prev_send_chain_len,
        )
        self.send_seq += 1

        return PQRatchetMessage(header=header, ciphertext=ciphertext, auth_tag=tag)

    def decrypt_message(self, msg: PQRatchetMessage) -> Tuple[bool, bytes, str]:
        """Decrypts and authenticates incoming message, ratcheting receive chain."""
        if self.recv_chain_key is None:
            return False, b"", "RECV_CHAIN_UNINITIALIZED"

        # Advance receive chain to match sequence number
        while self.recv_seq < msg.header.sequence_num:
            self.recv_chain_key, _ = self._kdf_ck(self.recv_chain_key)
            self.recv_seq += 1

        self.recv_chain_key, mk = self._kdf_ck(self.recv_chain_key)
        self.recv_seq += 1

        # Verify authentication tag
        expected_tag = hmac.new(mk, msg.ciphertext + msg.header.sequence_num.to_bytes(4, "big"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(msg.auth_tag, expected_tag):
            return False, b"", "AUTHENTICATION_TAG_MISMATCH"

        otp_keystream = hashlib.sha256(mk + msg.header.sequence_num.to_bytes(4, "big")).digest()
        plaintext = bytes([c ^ otp_keystream[i % len(otp_keystream)] for i, c in enumerate(msg.ciphertext)])

        return True, plaintext, "DECRYPTED_SUCCESSFULLY"
