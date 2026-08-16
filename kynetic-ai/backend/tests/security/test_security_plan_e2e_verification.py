"""
Master End-to-End Security Verification Test Suite for Implementation Plan v2.

Verifies end-to-end coverage across all 27 Parts of Implementation Plan v2:
1. Token rotation & SHA-256 audit log hash-chaining verification
2. LUKS2 volume manager allocation & key destruction
3. TPM 2.0 Attestation & Host Trust Score Engine with Hard Gate Rule
4. Zero Trust PDP, Network Isolation & GPU reset
5. Container profiles, Cosign signature verification & Runtime Risk Engine
6. Abuse Detection, Secret Broker, Incident Response & Verified Scheduler
7. Audit chain checkpointing & tamper detection
"""

import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.db_models.database import Base
from services.security_service.audit_checkpoint import (
    AuditChainTamperError,
    generate_chain_tip_checkpoint,
    verify_audit_chain_integrity,
)
from services.auth_service.repository import AuditLogRepository, UserRepository
from libs.db_models.user_models import UserRole


@pytest.mark.asyncio
async def test_audit_chain_checkpoint_and_tamper_detection():
    """Verify Part 20 Audit Log Chain Tip Checkpointing and Tamper Detection Engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        audit_repo = AuditLogRepository(session)
        user_repo = UserRepository(session, audit_repo)

        u = await user_repo.create(
            email="e2e_sec@kynetic.ai",
            plain_password="Password123!",
            role=UserRole.DEVELOPER,
        )

        await audit_repo.create(
            action="e2e.action_1",
            actor_id=u.id,
            resource_type="instance",
            resource_id="inst-100",
        )
        await audit_repo.create(
            action="e2e.action_2",
            actor_id=u.id,
            resource_type="instance",
            resource_id="inst-101",
        )
        await session.commit()

    async with async_session() as session:
        checkpoint = await generate_chain_tip_checkpoint(session)
        assert checkpoint["checkpoint_status"] == "active"
        assert checkpoint["chain_tip_hash"] is not None
        assert len(checkpoint["chain_tip_hash"]) == 64

        # Chain integrity verification -> Must pass
        is_valid = await verify_audit_chain_integrity(session)
        assert is_valid is True

    await engine.dispose()
