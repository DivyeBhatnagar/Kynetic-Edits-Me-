"""
Auth Service — JWT and password hashing utilities.

Design decisions:
- Short-lived access tokens (15 min default) + long-lived refresh tokens (30 days).
- Refresh tokens are stored as SHA-256 hashes in DB — raw token only returned once.
- Passwords hashed with passlib's bcrypt backend.
- python-jose used for JWT encode/decode.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from jose import JWTError, jwt
from passlib.context import CryptContext

from services.auth_service.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# ---------------------------------------------------------------------------
# Password hashing — bcrypt via passlib
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=settings.bcrypt_rounds)


def hash_password(plain_password: str) -> str:
    """Return bcrypt hash of the plain-text password."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plain_password matches the bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ---------------------------------------------------------------------------
# JWT — access tokens
# ---------------------------------------------------------------------------
def create_access_token(
    user_id: uuid.UUID,
    role: str,
    *,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a short-lived JWT access token.

    Claims:
        sub  — user UUID (as string)
        role — user role
        iat  — issued-at timestamp
        exp  — expiry timestamp
        jti  — unique token ID (for future revocation if needed)
    """
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.access_token_expire_minutes))

    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT access token.
    Raises jose.JWTError on invalid/expired token.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        options={"verify_exp": True},
    )


# ---------------------------------------------------------------------------
# Refresh tokens
# ---------------------------------------------------------------------------
def generate_refresh_token() -> tuple[str, str]:
    """
    Generate a cryptographically random refresh token.

    Returns:
        (raw_token, token_hash) — store token_hash in DB; return raw_token to client.
    """
    raw_token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def hash_refresh_token(raw_token: str) -> str:
    """Hash a raw refresh token for DB lookup."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def refresh_token_expires_at() -> datetime:
    """Return the expiry datetime for a new refresh token."""
    return datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)


# ---------------------------------------------------------------------------
# OTP utilities
# ---------------------------------------------------------------------------
def generate_otp() -> str:
    """Return a 6-digit OTP string."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    """
    Hash an OTP for storage.
    Uses bcrypt (same pwd_context) so it's resistant to offline cracking
    even for 6-digit values.
    """
    return pwd_context.hash(otp)


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Return True if plain_otp matches the stored hash."""
    return pwd_context.verify(plain_otp, hashed_otp)
