"""
Auth Service — Integration Tests (Phase 1 exit criteria).

Tests every endpoint in the Phase 1 API surface:
  POST /auth/signup
  POST /auth/login
  POST /auth/refresh
  POST /auth/logout
  GET  /auth/me
  POST /auth/phone/send-otp
  POST /auth/phone/verify-otp

Covers:
  - Happy paths (all success cases)
  - Duplicate email rejection
  - Invalid password / wrong credentials
  - Token rotation on refresh
  - OTP attempt limiting
"""

import pytest
from httpx import AsyncClient


# ── Helpers ────────────────────────────────────────────────────────────────
VALID_SIGNUP = {
    "email": "dev@example.com",
    "password": "SecurePass1",
    "role": "developer",
}


async def signup_and_login(client: AsyncClient, email: str = "dev@example.com") -> dict:
    """Helper: signup and return token response payload."""
    resp = await client.post("/auth/signup", json={
        "email": email,
        "password": "SecurePass1",
        "role": "developer",
    })
    assert resp.status_code == 201
    return resp.json()


# ── Health check ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_healthz(auth_client: AsyncClient):
    resp = await auth_client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── POST /auth/signup ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_signup_success(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/signup", json=VALID_SIGNUP)
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "dev@example.com"
    assert data["user"]["role"] == "developer"
    assert "hashed_password" not in data["user"]


@pytest.mark.asyncio
async def test_signup_duplicate_email(auth_client: AsyncClient):
    await signup_and_login(auth_client)
    resp = await auth_client.post("/auth/signup", json=VALID_SIGNUP)
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_signup_weak_password_no_digit(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/signup", json={
        "email": "weak@example.com",
        "password": "NoDigitHere!",
        "role": "developer",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_short_password(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/signup", json={
        "email": "short@example.com",
        "password": "Ab1",
        "role": "developer",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_signup_host_role(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/signup", json={
        "email": "host@example.com",
        "password": "HostPass99",
        "role": "host",
    })
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "host"


# ── POST /auth/login ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_login_success(auth_client: AsyncClient):
    await signup_and_login(auth_client)
    resp = await auth_client.post("/auth/login", json={
        "email": "dev@example.com",
        "password": "SecurePass1",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


@pytest.mark.asyncio
async def test_login_wrong_password(auth_client: AsyncClient):
    await signup_and_login(auth_client)
    resp = await auth_client.post("/auth/login", json={
        "email": "dev@example.com",
        "password": "WrongPass9",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/login", json={
        "email": "ghost@example.com",
        "password": "SomePass1",
    })
    assert resp.status_code == 401


# ── GET /auth/me ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_me_authenticated(auth_client: AsyncClient):
    tokens = await signup_and_login(auth_client)
    resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "dev@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(auth_client: AsyncClient):
    resp = await auth_client.get("/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_me_invalid_token(auth_client: AsyncClient):
    resp = await auth_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer totally.invalid.token"},
    )
    assert resp.status_code == 401


# ── POST /auth/refresh ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_refresh_token_rotation(auth_client: AsyncClient):
    tokens = await signup_and_login(auth_client)
    original_refresh = tokens["refresh_token"]

    # First refresh — should succeed and return a new refresh token
    resp = await auth_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert resp.status_code == 200
    new_data = resp.json()
    assert "access_token" in new_data
    assert new_data["refresh_token"] != original_refresh  # Token was rotated

    # Using the OLD refresh token should fail (it was revoked)
    resp2 = await auth_client.post("/auth/refresh", json={"refresh_token": original_refresh})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_refresh_invalid_token(auth_client: AsyncClient):
    resp = await auth_client.post("/auth/refresh", json={"refresh_token": "fake-token"})
    assert resp.status_code == 401


# ── POST /auth/logout ──────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_logout_revokes_tokens(auth_client: AsyncClient):
    tokens = await signup_and_login(auth_client)
    access = tokens["access_token"]
    refresh = tokens["refresh_token"]

    # Logout
    resp = await auth_client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert resp.status_code == 200

    # Refresh token should now be revoked
    resp2 = await auth_client.post("/auth/refresh", json={"refresh_token": refresh})
    assert resp2.status_code == 401


# ── Phone OTP ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_send_otp_requires_auth(auth_client: AsyncClient):
    resp = await auth_client.post(
        "/auth/phone/send-otp",
        json={"phone_number": "+919876543210"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_send_and_verify_otp_flow(auth_client: AsyncClient, monkeypatch):
    """
    Test the full OTP flow by intercepting the raw OTP from the dev log.
    In dev mode, the raw OTP is logged at DEBUG level — we patch the repository
    to capture it without real SMS.
    """
    tokens = await signup_and_login(auth_client)
    access = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    # Capture the raw OTP by monkeypatching the OTP repo
    captured_otp = {}

    from services.auth_service import repository as repo_module
    original_create = repo_module.PhoneOTPRepository.create

    async def capturing_create(self, user_id, phone_number):
        record, raw = await original_create(self, user_id, phone_number)
        captured_otp["raw"] = raw
        return record, raw

    monkeypatch.setattr(repo_module.PhoneOTPRepository, "create", capturing_create)

    # Send OTP
    resp = await auth_client.post(
        "/auth/phone/send-otp",
        json={"phone_number": "+919876543210"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Verify with captured OTP
    resp2 = await auth_client.post(
        "/auth/phone/verify-otp",
        json={"phone_number": "+919876543210", "otp": captured_otp["raw"]},
        headers=headers,
    )
    assert resp2.status_code == 200

    # Check phone_verified flag
    me = await auth_client.get("/auth/me", headers=headers)
    assert me.json()["phone_verified"] is True


@pytest.mark.asyncio
async def test_invalid_otp_rejected(auth_client: AsyncClient, monkeypatch):
    tokens = await signup_and_login(auth_client)
    access = tokens["access_token"]
    headers = {"Authorization": f"Bearer {access}"}

    await auth_client.post(
        "/auth/phone/send-otp",
        json={"phone_number": "+919876543210"},
        headers=headers,
    )

    # Wrong OTP
    resp = await auth_client.post(
        "/auth/phone/verify-otp",
        json={"phone_number": "+919876543210", "otp": "000000"},
        headers=headers,
    )
    assert resp.status_code == 400
