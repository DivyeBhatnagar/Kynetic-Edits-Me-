"""
Host Service — mTLS Certificate Authority utilities.

When a Host Agent registers, the backend issues it a client certificate
signed by Kynetic's internal CA. The agent uses this cert for all subsequent
connections, implementing Security Pillar 1 (mTLS for host ↔ backend).

Design:
- Self-signed CA per environment (dev: generated at startup, prod: HSM-backed)
- Client certs have 365-day validity (configurable)
- Cert fingerprint (SHA-256) stored in the hosts table for future revocation
- This is the MVP-tier mTLS baseline; full mutual cert chain verification
  and OCSP stapling are Post-MVP (Pillar 1 advanced tier)
"""

import hashlib
import ipaddress
from datetime import UTC, datetime, timedelta

import structlog
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = structlog.get_logger(__name__)


def generate_ca_keypair() -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    """
    Generate a new self-signed CA keypair for development / test use.
    In production, the CA private key is HSM-backed and never loaded into memory.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Kynetic AI"),
        x509.NameAttribute(NameOID.COMMON_NAME, "Kynetic Internal CA"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(key, hashes.SHA256())
    )
    logger.info("ca_keypair_generated")
    return key, cert


def issue_client_certificate(
    host_id: str,
    user_id: str,
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    validity_days: int = 365,
) -> tuple[str, str, str]:
    """
    Issue a client certificate for a Host Agent.

    The Common Name encodes both host_id and user_id so the server
    can identify which host and user a connection belongs to from the cert alone.

    Returns:
        (cert_pem, key_pem, cert_fingerprint_hex)
        - cert_pem and key_pem are returned to the agent (once, at registration)
        - cert_fingerprint_hex is stored in the hosts table
    """
    client_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Kynetic AI"),
        x509.NameAttribute(
            NameOID.COMMON_NAME,
            f"host:{host_id}",
        ),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(client_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(UTC))
        .not_valid_after(datetime.now(UTC) + timedelta(days=validity_days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = client_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    # SHA-256 fingerprint of the DER-encoded cert — stored in DB
    fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()

    logger.info(
        "client_cert_issued",
        host_id=host_id,
        user_id=user_id,
        fingerprint=fingerprint[:16] + "...",
        expires_at=(datetime.now(UTC) + timedelta(days=validity_days)).isoformat(),
    )
    return cert_pem, key_pem, fingerprint


def load_ca_from_pem(cert_pem: str, key_pem: str) -> tuple:
    """Load an existing CA cert + key from PEM strings (used in production)."""
    from cryptography.hazmat.primitives.serialization import load_pem_private_key
    ca_key = load_pem_private_key(key_pem.encode(), password=None)
    ca_cert = x509.load_pem_x509_certificate(cert_pem.encode())
    return ca_key, ca_cert
