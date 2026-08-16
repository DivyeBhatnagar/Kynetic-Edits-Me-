"""
Unit test suite for Security Enhancements Implementation Plan v2:
1. Refresh Token Single-Use Rotation & Family Reuse Revocation
2. Audit Log SHA-256 Hash Chaining (prev_hash, entry_hash)
"""

import hashlib
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.db_models.database import Base
from libs.db_models.user_models import AuditLog, RefreshToken, User, UserRole
from services.auth_service.repository import AuditLogRepository, RefreshTokenRepository, UserRepository
from services.auth_service.security import generate_refresh_token, hash_refresh_token


@pytest.mark.asyncio
async def test_audit_log_hash_chaining():
    """Verify that AuditLog entries form a cryptographically verifiable SHA-256 hash chain."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        audit_repo = AuditLogRepository(session)
        user_id = uuid.uuid4()

        # Log 1
        log1 = await audit_repo.create(
            action="test.action_1",
            actor_id=user_id,
            resource_type="test_res",
            resource_id="res_1",
        )
        assert log1.prev_hash == "GENESIS_HASH_CHAIN_ROOT_0000000000000000000000000000000000000000"
        assert log1.entry_hash is not None
        assert len(log1.entry_hash) == 64

        # Log 2
        log2 = await audit_repo.create(
            action="test.action_2",
            actor_id=user_id,
            resource_type="test_res",
            resource_id="res_2",
        )
        assert log2.prev_hash == log1.entry_hash
        assert log2.entry_hash is not None
        assert len(log2.entry_hash) == 64
        assert log2.entry_hash != log1.entry_hash

        # Commit and query back
        await session.commit()

    async with async_session() as session:
        result = await session.execute(select(AuditLog).order_by(AuditLog.created_at.asc()))
        logs = result.scalars().all()
        assert len(logs) == 2
        assert logs[0].prev_hash == "GENESIS_HASH_CHAIN_ROOT_0000000000000000000000000000000000000000"
        assert logs[1].prev_hash == logs[0].entry_hash

    await engine.dispose()


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_reuse_detection():
    """Verify single-use refresh token rotation and family revocation on token reuse attempt."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        audit_repo = AuditLogRepository(session)
        user_repo = UserRepository(session, audit_repo)
        refresh_repo = RefreshTokenRepository(session, audit_repo)

        user = await user_repo.create(
            email="sec_test@kynetic.ai",
            plain_password="Password123!",
            role=UserRole.DEVELOPER,
        )

        raw_token1, token_hash1 = generate_refresh_token()
        t1 = await refresh_repo.create(user.id, raw_token1)
        family_id = t1.family_id
        assert family_id is not None

        # Rotation 1 (Valid)
        rotate1 = await refresh_repo.rotate(raw_token1)
        assert rotate1 is not None
        raw_token2, t2 = rotate1
        assert t2.family_id == family_id
        assert raw_token2 != raw_token1

        # Check t1 marked used
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash1)
        res = await session.execute(stmt)
        t1_fetched = res.scalar_one()
        assert t1_fetched.used_at is not None

        # REUSE ATTEMPT: Try to use raw_token1 again!
        reuse_attempt = await refresh_repo.rotate(raw_token1)
        assert reuse_attempt is None  # Must be rejected!

        # Verify that ENTIRE token family (including t2) is now revoked!
        stmt_family = select(RefreshToken).where(RefreshToken.family_id == family_id)
        res_family = await session.execute(stmt_family)
        family_tokens = res_family.scalars().all()
        assert len(family_tokens) == 2
        for tok in family_tokens:
            assert tok.is_revoked is True
            assert tok.revoked_at is not None

    await engine.dispose()
