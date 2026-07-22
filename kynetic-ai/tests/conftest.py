"""
Pytest configuration for Kynetic AI tests.

Sets up:
- Async test database (separate test DB, rebuilt per session)
- Overrides FastAPI dependencies (DB session, settings)
- httpx AsyncClient fixture for endpoint testing
"""

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from libs.db_models.database import Base, get_db_session
from services.auth_service.main import app as auth_app

# ── Test database ──────────────────────────────────────────────────────────
TEST_DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://kynetic:kynetic@localhost:5432/kynetic_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)


# ── Session-scoped: create / drop all tables ───────────────────────────────
@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create all tables at session start, drop at session end."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


# ── Function-scoped: clean DB between tests ────────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_test_db):
    """Truncate all tables between tests for isolation."""
    yield
    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


# ── DB session fixture ─────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        yield session


# ── Override FastAPI DB dependency ─────────────────────────────────────────
async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ── Auth service test client ───────────────────────────────────────────────
@pytest_asyncio.fixture
async def auth_client() -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient pointed at the auth service FastAPI app."""
    auth_app.dependency_overrides[get_db_session] = _override_get_db_session
    async with AsyncClient(
        transport=ASGITransport(app=auth_app),
        base_url="http://test",
    ) as client:
        yield client
    auth_app.dependency_overrides.clear()
