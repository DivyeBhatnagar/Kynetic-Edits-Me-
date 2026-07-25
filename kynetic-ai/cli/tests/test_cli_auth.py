"""
Unit tests for Python Kynetic CLI Auth & Config.
"""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from kynetic_cli.auth import AuthClient
from kynetic_cli.cli import cli
from kynetic_cli.config import (
    clear_credentials,
    load_config,
    load_credentials,
    save_config,
    save_credentials,
)


def test_config_save_load(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    cfg = load_config()
    assert cfg["api_url"] == "http://localhost:8000"

    cfg["default_region"] = "eu-west-1"
    save_config(cfg)

    loaded = load_config()
    assert loaded["default_region"] == "eu-west-1"


def test_credentials_save_load_clear(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    assert load_credentials() is None

    creds = {"access_token": "test-jwt", "email": "dev@kynetic.ai"}
    save_credentials(creds)

    loaded = load_credentials()
    assert loaded["access_token"] == "test-jwt"

    # Verify file permissions
    creds_file = tmp_path / ".kynetic" / "credentials"
    assert creds_file.exists()
    assert oct(creds_file.stat().st_mode & 0o777) == "0o600"

    clear_credentials()
    assert load_credentials() is None


@patch("httpx.Client.post")
def test_auth_request_device_code(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "device_code": "dev-123",
        "user_code": "ABCD-5678",
        "verification_uri": "http://localhost:8000/auth/device/verify",
        "expires_in": 600,
        "interval": 5,
    }
    mock_post.return_value = mock_resp

    client = AuthClient("http://localhost:8000")
    data = client.request_device_code()

    assert data["device_code"] == "dev-123"
    assert data["user_code"] == "ABCD-5678"


def test_cli_version_cmd():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "Phase A — Foundations, 100% Python Stack" in result.output
