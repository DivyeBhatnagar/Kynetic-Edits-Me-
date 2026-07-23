"""
Local conftest for reputation_pricing_service tests.

Overrides the root-level conftest DB session fixture so that
pure-Python unit tests (reputation.py, pricing.py) never try
to connect to PostgreSQL.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def override_db_session(monkeypatch_session=None):
    """No-op override — these tests are pure Python and need no DB."""
    return None


# Prevent asyncpg from being imported at collection time via root conftest
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"
