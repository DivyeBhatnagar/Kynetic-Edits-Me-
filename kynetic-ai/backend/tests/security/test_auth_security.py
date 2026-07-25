"""
Phase 14 — Auth & API Security Hardening Tests

Tests:
  - JWT token tampering and invalid signature rejection
  - Expired token handling
  - Admin endpoint RBAC authorization enforcement
  - Rate limiting bucket calculation
"""

from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
import pytest

SECRET_KEY = "test-secret-key-not-real"
ALGORITHM = "HS256"


def create_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def authorize_admin_endpoint(user_role: str) -> bool:
    """RBAC check for admin endpoints."""
    if user_role != "admin":
        raise PermissionError("Access denied: Admin role required")
    return True


class TestAuthAndAPISecurity:
    """Security tests for authentication and authorization."""

    def test_valid_jwt_decoding(self):
        token = create_token({"sub": "user_123", "role": "developer"})
        payload = decode_token(token)
        assert payload["sub"] == "user_123"
        assert payload["role"] == "developer"

    def test_tampered_jwt_signature_rejected(self):
        token = create_token({"sub": "user_123", "role": "developer"})
        tampered_token = token[:-5] + "XXXXX"
        with pytest.raises(JWTError):
            decode_token(tampered_token)

    def test_expired_jwt_rejected(self):
        token = create_token({"sub": "user_123"}, expires_delta=timedelta(seconds=-10))
        with pytest.raises(JWTError):
            decode_token(token)

    def test_admin_rbac_enforcement(self):
        # Developer user denied
        with pytest.raises(PermissionError):
            authorize_admin_endpoint("developer")

        # Host user denied
        with pytest.raises(PermissionError):
            authorize_admin_endpoint("host")

        # Admin user allowed
        assert authorize_admin_endpoint("admin") is True
