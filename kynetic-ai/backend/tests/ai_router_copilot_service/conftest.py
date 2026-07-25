"""
conftest.py for ai_router_copilot_service tests.

The ranking tests are pure unit tests (no DB needed).
Override the autouse DB fixtures from the root conftest so they
don't attempt a PostgreSQL connection during this test suite.
"""

import pytest
import pytest_asyncio


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    """
    Override root conftest's setup_test_db.
    These tests don't need a real DB — the ranking function is pure Python.
    """
    yield


@pytest_asyncio.fixture(autouse=True)
async def clean_db(setup_test_db):
    """Override root conftest's clean_db — no-op for unit tests."""
    yield
