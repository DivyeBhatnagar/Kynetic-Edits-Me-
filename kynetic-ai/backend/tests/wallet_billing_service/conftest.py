import pytest


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    yield


@pytest.fixture(autouse=True)
def clean_db(setup_test_db):
    yield
