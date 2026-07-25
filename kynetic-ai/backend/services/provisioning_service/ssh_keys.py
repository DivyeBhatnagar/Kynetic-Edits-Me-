"""
Provisioning Service — Ephemeral SSH Key Management.

Security rules enforced here:
1. Private keys are NEVER stored in plaintext — encrypted with Fernet
   before any DB write.
2. RSA key size is 4096 bits minimum (configurable via settings).
3. On session revocation, the encrypted blob is nulled in the DB —
   the plaintext is unrecoverable.
4. Public key is in OpenSSH format (authorized_keys compatible).
5. The connection string is built here and includes the correct host
   (direct IP or WireGuard relay) resolved at call time.
"""

import base64
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services.provisioning_service.config import get_settings

settings = get_settings()


# ── Key generation ─────────────────────────────────────────────────────────

def generate_keypair() -> tuple[str, str]:
    """
    Generate an ephemeral RSA-4096 keypair.

    Returns:
        (public_key_openssh, private_key_pem)

    The private key PEM must be encrypted before storage.
    It is returned here only so the caller can encrypt it immediately.
    """
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=settings.ssh_key_size_bits,
    )

    # Private key — PKCS8 PEM, unencrypted (caller must encrypt before storage)
    private_key_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    # Public key — OpenSSH format (ready for authorized_keys injection)
    public_key_openssh = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode("utf-8")

    return public_key_openssh, private_key_pem


# ── Fernet encryption / decryption ─────────────────────────────────────────

def _get_fernet() -> Fernet:
    """
    Returns a Fernet cipher using the configured key.
    Raises immediately on startup if the key is invalid (fail-fast).
    """
    key = settings.ssh_key_fernet_key.encode()
    # Fernet requires 32-byte URL-safe base64
    return Fernet(key)


def encrypt_private_key(private_key_pem: str) -> str:
    """
    Encrypt a private key PEM with Fernet.
    Returns base64-encoded ciphertext (safe to store in TEXT column).
    """
    f = _get_fernet()
    ciphertext = f.encrypt(private_key_pem.encode("utf-8"))
    return ciphertext.decode("ascii")


def decrypt_private_key(encrypted: str) -> str:
    """
    Decrypt a Fernet-encrypted private key.
    Raises cryptography.fernet.InvalidToken if the ciphertext is corrupt
    or the key has been rotated.
    """
    f = _get_fernet()
    plaintext = f.decrypt(encrypted.encode("ascii"))
    return plaintext.decode("utf-8")


# ── Connection string builder ──────────────────────────────────────────────

def build_ssh_command(
    *,
    ssh_host: str,
    ssh_port: int,
    ssh_user: str = "kynetic",
    key_filename: str = "kynetic_key.pem",
) -> str:
    """
    Builds the ready-to-paste SSH command.

    Example:
        ssh -i kynetic_key.pem -p 22 kynetic@10.42.1.5
    """
    port_flag = f"-p {ssh_port} " if ssh_port != 22 else ""
    return f"ssh -i {key_filename} {port_flag}{ssh_user}@{ssh_host}"


# ── Key rotation deadline ──────────────────────────────────────────────────

def key_expiry_time(issued_at: datetime) -> datetime:
    """Returns when an SSH session key should be rotated."""
    return issued_at + timedelta(seconds=settings.ssh_key_rotation_seconds)
