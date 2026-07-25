"""
Local conftest for security_service tests.

The security tests are purely unit tests — no database, no HTTP, no Redis.
This conftest overrides the global session-scoped `setup_test_db` and
`clean_db` autouse fixtures so they become no-ops for this subtree.
"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Override: security tests need no database setup."""
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_test_db):
    """Override: security tests have nothing to clean."""
    yield
