"""
Phase 20 — Attestation Gateway & Sealed Secret Injection Pipeline
Ensures job secrets (SSH private keys, model decryption keys, API tokens)
are sealed (encrypted) to the hardware enclave's public key.
The Host OS sees ONLY high-entropy ciphertext.
"""

import os
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class AttestationSealer:
    @staticmethod
    def seal_secret_for_enclave(secret_bytes: bytes, enclave_pubkey_der: bytes) -> bytes:
        """
        Encrypts secret_bytes using ECDH ephemeral key exchange against
        the verified hardware enclave's public key.
        """
        enclave_pubkey = serialization.load_der_public_key(enclave_pubkey_der)
        ephemeral_privkey = ec.generate_private_key(ec.SECP384R1())
        shared_secret = ephemeral_privkey.exchange(ec.ECDH(), enclave_pubkey)

        derived_aes_key = HKDF(
            algorithm=hashes.SHA384(),
            length=32,
            salt=None,
            info=b"kynetic-zero-trust-sealed-secret-v4",
        ).derive(shared_secret)

        nonce = os.urandom(12)
        ciphertext = AESGCM(derived_aes_key).encrypt(nonce, secret_bytes, associated_data=None)

        ephemeral_pubkey_bytes = ephemeral_privkey.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        # Returns: Ephemeral Public Key Header + Nonce + Ciphertext
        return ephemeral_pubkey_bytes + nonce + ciphertext

    @staticmethod
    def unseal_secret_in_enclave(sealed_bytes: bytes, enclave_privkey: ec.EllipticCurvePrivateKey) -> bytes:
        """
        Executed strictly INSIDE hardware enclave memory to unseal secret.
        """
        # SubjectPublicKeyInfo DER length for SECP384R1 is 120 bytes
        header_len = 120
        nonce_len = 12
        ephemeral_pubkey_bytes = sealed_bytes[:header_len]
        nonce = sealed_bytes[header_len : header_len + nonce_len]
        ciphertext = sealed_bytes[header_len + nonce_len :]

        ephemeral_pubkey = serialization.load_der_public_key(ephemeral_pubkey_bytes)
        shared_secret = enclave_privkey.exchange(ec.ECDH(), ephemeral_pubkey)

        derived_aes_key = HKDF(
            algorithm=hashes.SHA384(),
            length=32,
            salt=None,
            info=b"kynetic-zero-trust-sealed-secret-v4",
        ).derive(shared_secret)

        return AESGCM(derived_aes_key).decrypt(nonce, ciphertext, associated_data=None)
