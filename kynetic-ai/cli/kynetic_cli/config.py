"""
Config and Credentials Manager for Kynetic CLI.

Stores configuration at ~/.kynetic/config.json and sensitive auth credentials
at ~/.kynetic/credentials with strict file mode 0600.
"""

import json
import os
from pathlib import Path
from typing import Any


def get_kynetic_dir() -> Path:
    kynetic_dir = Path.home() / ".kynetic"
    kynetic_dir.mkdir(parents=True, exist_ok=True)
    return kynetic_dir


def get_config_path() -> Path:
    return get_kynetic_dir() / "config.json"


def get_credentials_path() -> Path:
    return get_kynetic_dir() / "credentials"


def load_config() -> dict[str, Any]:
    default_config = {
        "api_url": os.getenv("KYNETIC_API_URL", "http://localhost:8000"),
        "default_region": "us-east-1",
        "output_format": "text",
        "currency": "USD",
    }
    path = get_config_path()
    if not path.exists():
        save_config(default_config)
        return default_config

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_config.update(data)
            return default_config
    except Exception:
        return default_config


def save_config(cfg: dict[str, Any]) -> None:
    path = get_config_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_credentials() -> dict[str, Any] | None:
    path = get_credentials_path()
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_credentials(creds: dict[str, Any]) -> None:
    path = get_credentials_path()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(creds, f, indent=2)
    # Enforce strict 0600 permissions
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass


def clear_credentials() -> None:
    path = get_credentials_path()
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
