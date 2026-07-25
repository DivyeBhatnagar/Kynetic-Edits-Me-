# Phase 17 legal tests conftest
import os
import pytest
import pytest_asyncio

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-real")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """No-op override of root conftest fixture."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_test_db):
    """No-op override of root conftest fixture."""
    yield
