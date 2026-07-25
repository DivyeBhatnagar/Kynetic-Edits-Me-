"""
Local conftest for wallet_billing_service unit tests.

Overrides the session-scoped setup_test_db fixture from the root conftest
so unit tests (Razorpay, GST calculation, etc.) can run WITHOUT a database.
"""

import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """
    Override root conftest DB setup.
    Unit tests in this directory don't need a DB connection.
    """
    yield


@pytest.fixture(autouse=True)
def clean_db(setup_test_db):
    """Override: no DB cleanup needed for pure unit tests."""
    yield
