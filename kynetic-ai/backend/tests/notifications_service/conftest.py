"""
Local conftest for notifications_service unit tests.

Overrides the session-scoped setup_test_db fixture from the root conftest
so unit tests can run WITHOUT a database.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """No DB needed for notifications unit tests."""
    yield


@pytest.fixture(autouse=True)
def clean_db(setup_test_db):
    """Override: no DB cleanup needed for pure unit tests."""
    yield
