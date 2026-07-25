"""
Unit & Integration Test Suite for v8 Features 2 & 3:
Feature 2: Host Reputation System (events, exponential decay, anti-gaming, admin overrides)
Feature 3: Verified Hosts (Silver/Gold/Enterprise, document submission, admin queue, revocation cascade)
"""

import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from libs.db_models.user_models import User, UserRole
from libs.db_models.host_models import Host, HostStatus, OSType, HostVerification
from libs.db_models.reputation_pricing_models import ReputationEvent, ReputationScore
from services.reputation_pricing_service.main import app as rep_app
from services.host_service.main import app as host_app
from services.reputation_pricing_service.reputation_engine import (
    emit_reputation_event,
    compute_decayed_reputation,
    get_host_reputation_history,
    apply_manual_penalty,
    apply_manual_restore,
)
from services.host_service.verification_service import (
    apply_for_verification,
    evaluate_automatic_silver_verification,
    evaluate_gold_eligibility,
    process_admin_review,
    revoke_host_verification,
    get_verification_status,
)


from tests.conftest import _override_get_db_session, get_db_session


@pytest_asyncio.fixture
async def rep_client():
    rep_app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=rep_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    rep_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def host_client():
    host_app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=host_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
    host_app.dependency_overrides.clear()


# ── Feature 2 Unit & Engine Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_emit_reputation_event_append_only(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="repuser1@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    ev = await emit_reputation_event(db_session, host_id, "job_completed", impact_delta=0.05, metadata={"job_id": "j123"})
    await db_session.commit()

    assert ev.id is not None
    assert ev.event_type == "job_completed"
    assert float(ev.impact_delta) == 0.05

    history = await get_host_reputation_history(db_session, host_id)
    assert len(history) == 1
    assert history[0]["event_type"] == "job_completed"
    assert history[0]["metadata"]["job_id"] == "j123"


@pytest.mark.asyncio
async def test_compute_decayed_reputation(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="repuser2@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    # Emit 5 completed jobs and 1 failed job
    for _ in range(5):
        await emit_reputation_event(db_session, host_id, "job_completed")
    await emit_reputation_event(db_session, host_id, "job_failed")
    await db_session.commit()

    res = await compute_decayed_reputation(db_session, host_id)
    await db_session.commit()

    assert res["host_id"] == str(host_id)
    assert res["completed_jobs"] == 5
    assert res["failed_jobs"] == 1
    assert round(res["job_success_rate"], 3) == round(5 / 6, 3)
    assert 0.0 <= res["composite_score"] <= 1.0


@pytest.mark.asyncio
async def test_anti_gaming_cancelled_jobs_penalty(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="repuser3@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    # Host attempts volume gaming by self-cancelling 10 jobs
    for _ in range(10):
        await emit_reputation_event(db_session, host_id, "job_cancelled")
    await db_session.commit()

    res = await compute_decayed_reputation(db_session, host_id)
    await db_session.commit()

    assert res["cancelled_jobs"] == 10
    # Composite score should decrease below starting baseline 0.50 due to cancellation penalty (-0.02 * 10 = -0.20 -> 0.30)
    assert res["composite_score"] < 0.50


@pytest.mark.asyncio
async def test_automatic_penalty_and_trust_state(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="repuser4@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    # Emit severe violation flag
    await emit_reputation_event(db_session, host_id, "violation_flagged", metadata={"reason": "Benchmark spoofing detected"})
    await db_session.commit()

    # Refresh host object
    h_stmt = select(Host).where(Host.id == host_id)
    h_res = await db_session.execute(h_stmt)
    updated_host = h_res.scalars().first()

    assert updated_host.trust_state == "flagged"


@pytest.mark.asyncio
async def test_admin_manual_penalty_and_restore(db_session: AsyncSession, rep_client: AsyncClient):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="adminrep@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    # Apply admin penalty
    p_resp = await rep_client.post(
        f"/v1/admin/hosts/{host_id}/reputation/penalty",
        json={"impact_delta": -0.30, "reason": "Suspicious network pattern"}
    )
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert p_data["status"] == "applied"
    assert p_data["impact_delta"] == -0.30

    # Apply admin restore
    r_resp = await rep_client.post(
        f"/v1/admin/hosts/{host_id}/reputation/restore",
        json={"impact_delta": 0.30, "reason": "Appeal accepted"}
    )
    assert r_resp.status_code == 200
    r_data = r_resp.json()
    assert r_data["status"] == "applied"
    assert r_data["impact_delta"] == 0.30

    # Verify event history
    h_resp = await rep_client.get(f"/v1/hosts/{host_id}/reputation/history")
    assert h_resp.status_code == 200
    events = h_resp.json()
    assert len(events) >= 2


# ── Feature 3 Verification Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_automatic_silver_verification(db_session: AsyncSession, host_client: AsyncClient):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="silverhost@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0")
    db_session.add(host)
    await db_session.commit()

    # Apply for Silver verification
    v_resp = await host_client.post(
        f"/hosts/{host_id}/verification/apply",
        json={"level": "silver", "documents": []}
    )
    assert v_resp.status_code == 201
    v_data = v_resp.json()
    assert v_data["level"] == "silver"
    assert v_data["status"] == "approved"

    # Check status endpoint
    st_resp = await host_client.get(f"/hosts/{host_id}/verification/status")
    assert st_resp.status_code == 200
    st_data = st_resp.json()
    assert st_data["verification_level"] == "silver"


@pytest.mark.asyncio
async def test_gold_verification_eligibility(db_session: AsyncSession):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="goldelig@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0", verification_level="silver")
    db_session.add(host)
    await db_session.commit()

    # Emit positive jobs to ensure score >= 0.70
    for _ in range(8):
        await emit_reputation_event(db_session, host_id, "job_completed")
    await compute_decayed_reputation(db_session, host_id)
    await db_session.commit()

    elig = await evaluate_gold_eligibility(db_session, host_id)
    assert elig["eligible"] is True
    assert elig["composite_score"] >= 0.70


@pytest.mark.asyncio
async def test_admin_verification_review_approve_reject(db_session: AsyncSession, host_client: AsyncClient):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="enterprise@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0", verification_level="silver")
    db_session.add(host)
    await db_session.commit()

    # Apply for Enterprise verification with business registration document
    v_resp = await host_client.post(
        f"/hosts/{host_id}/verification/apply",
        json={
            "level": "enterprise",
            "documents": [
                {"document_type": "business_registration", "storage_url": "s3://kynetic-docs/biz_reg.pdf"}
            ]
        }
    )
    assert v_resp.status_code == 201
    verif_id = v_resp.json()["verification_id"]

    # Admin approves application
    appr_resp = await host_client.post(f"/hosts/verifications/{verif_id}/approve")
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "approved"

    # Check updated verification level on host
    st_resp = await host_client.get(f"/hosts/{host_id}/verification/status")
    assert st_resp.json()["verification_level"] == "enterprise"


@pytest.mark.asyncio
async def test_admin_revocation_cascade(db_session: AsyncSession, host_client: AsyncClient):
    user_id = uuid.uuid4()
    user = User(id=user_id, email="revokehost@example.com", hashed_password="hash", role=UserRole.HOST)
    db_session.add(user)

    host_id = uuid.uuid4()
    host = Host(id=host_id, user_id=user_id, status=HostStatus.VERIFIED, os_type=OSType.LINUX, agent_version="1.0.0", verification_level="silver")
    db_session.add(host)
    await db_session.commit()

    # Revoke verification via admin endpoint
    rev_resp = await host_client.post(
        f"/hosts/{host_id}/verification/revoke",
        json={"reason": "Audit failure: forged documents"}
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json()["revoked"] is True

    # Check that host level was reset to unverified and trust state set to flagged
    st_resp = await host_client.get(f"/hosts/{host_id}/verification/status")
    st_data = st_resp.json()
    assert st_data["verification_level"] == "unverified"
    assert st_data["trust_state"] == "flagged"
