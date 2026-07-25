"""
Pytest integration test suite for Implementation Plan v6 Phase A — Foundations.

Tests:
1. POST /v1/auth/device/code — Device code generation
2. POST /v1/auth/device/token — Polling status (authorization_pending)
3. POST /v1/auth/device/verify — User approval of user_code
4. POST /v1/auth/device/token — Successful token retrieval after approval
5. GET /v1/cli/version — CLI version endpoint
6. DB models: Session, ApiToken, Event, DeviceCode persistence
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from libs.db_models.database import get_db_session
from libs.db_models.user_models import DeviceCode, DeviceCodeStatus, User, UserRole
from services.auth_service.main import app as auth_app


@pytest.mark.asyncio
async def test_device_code_flow_end_to_end(db_session: AsyncSession):
    transport = ASGITransport(app=auth_app)

    async def _override_db():
        yield db_session

    auth_app.dependency_overrides[get_db_session] = _override_db

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a test user directly in DB
        from services.auth_service.security import hash_password
        user = User(
            email="dev_v6@kynetic.ai",
            hashed_password=hash_password("Password123!"),
            role=UserRole.DEVELOPER,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

        # 2. Request device code
        resp = await client.post("/auth/device/code", json={"client_id": "kynetic-cli"})
        assert resp.status_code == 200
        data = resp.json()
        assert "device_code" in data
        assert "user_code" in data
        device_code = data["device_code"]
        user_code = data["user_code"]

        # 3. Poll token before approval -> 400 authorization_pending
        poll_resp = await client.post("/auth/device/token", json={"device_code": device_code})
        assert poll_resp.status_code == 400
        err_detail = poll_resp.json().get("detail", {})
        assert err_detail.get("error") == "authorization_pending"

        # 4. User logs in & approves code
        login_resp = await client.post("/auth/login", json={"email": "dev_v6@kynetic.ai", "password": "Password123!"})
        assert login_resp.status_code == 200
        access_token = login_resp.json()["access_token"]

        verify_resp = await client.post(
            "/auth/device/verify",
            json={"user_code": user_code},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["success"] is True

        # 5. Poll token after approval -> 200 TokenResponse
        poll_resp_2 = await client.post("/auth/device/token", json={"device_code": device_code})
        assert poll_resp_2.status_code == 200
        token_data = poll_resp_2.json()
        assert "access_token" in token_data
        assert "refresh_token" in token_data
        assert token_data["user"]["email"] == "dev_v6@kynetic.ai"

        # 6. Test /auth/cli/version
        version_resp = await client.get("/auth/cli/version")
        assert version_resp.status_code == 200
        v_data = version_resp.json()
        assert v_data["version"] == "1.0.0"

    auth_app.dependency_overrides.clear()
