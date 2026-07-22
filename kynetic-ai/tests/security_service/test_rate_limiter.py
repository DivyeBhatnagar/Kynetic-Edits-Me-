"""
Tests — Rate Limiter Middleware.

Tests the pure logic of RateLimitConfig.get_limit() and
the rate key generation without requiring a real Redis instance.
"""

import os
import time

import pytest

os.environ.setdefault("SCANNER_MOCK", "true")
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key")
os.environ.setdefault("ADMIN_JWT_SECRET_KEY", "test_admin_secret")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("PROVISIONING_SERVICE_URL", "http://localhost:8005")
os.environ.setdefault("WALLET_BILLING_SERVICE_URL", "http://localhost:8004")
os.environ.setdefault("HOST_SERVICE_URL", "http://localhost:8002")


from services.api_gateway.rate_limiter import RateLimitConfig, RateLimiterMiddleware


# ── RateLimitConfig ────────────────────────────────────────────────────────

def test_default_limit():
    config = RateLimitConfig(redis_url="redis://localhost:6379/0", default_rpm=60)
    assert config.get_limit("/listings") == 60
    assert config.get_limit("/marketplace/search") == 60


def test_auth_route_stricter():
    config = RateLimitConfig(redis_url="redis://localhost:6379/0", default_rpm=60)
    assert config.get_limit("/auth/login") == 20
    assert config.get_limit("/auth/register") == 20


def test_admin_route_limit():
    config = RateLimitConfig(redis_url="redis://localhost:6379/0", default_rpm=60)
    assert config.get_limit("/admin/kill-switch") == 30
    assert config.get_limit("/admin/security-events") == 30


def test_route_prefix_matching():
    """Auth limit should apply to any path starting with /auth."""
    config = RateLimitConfig(redis_url="redis://localhost:6379/0")
    assert config.get_limit("/auth/token/refresh") == 20
    assert config.get_limit("/auth/me") == 20


def test_custom_route_limit():
    config = RateLimitConfig(redis_url="redis://localhost:6379/0", default_rpm=100)
    config.route_limits["/special"] = 5
    assert config.get_limit("/special/endpoint") == 5
    assert config.get_limit("/other/endpoint") == 100


def test_default_rpm_custom():
    """Non-auth, non-admin routes should return the configured default_rpm."""
    config = RateLimitConfig(redis_url="redis://localhost:6379/0", default_rpm=120)
    assert config.get_limit("/instances") == 120
    assert config.get_limit("/wallet/balance") == 120


# ── Key generation ─────────────────────────────────────────────────────────

def test_rate_limit_key_format():
    """Keys should be per-IP, per-route-group, per-minute."""
    from unittest.mock import MagicMock
    config = RateLimitConfig(redis_url="redis://localhost:6379/0")
    app = MagicMock()
    middleware = RateLimiterMiddleware(app, config)

    key1 = middleware._rate_limit_key("1.2.3.4", "/auth/login")
    key2 = middleware._rate_limit_key("1.2.3.4", "/auth/register")
    key3 = middleware._rate_limit_key("5.6.7.8", "/auth/login")

    # Same IP + same route group → same key (within the same minute)
    assert key1 == key2  # Both /auth/* → same route group
    # Different IP → different key
    assert key1 != key3


def test_rate_limit_key_includes_minute():
    """Keys include the current minute bucket for time-windowing."""
    config = RateLimitConfig(redis_url="redis://localhost:6379/0")
    from unittest.mock import MagicMock
    app = MagicMock()
    middleware = RateLimiterMiddleware(app, config)

    key = middleware._rate_limit_key("1.2.3.4", "/listings")
    minute = int(time.time() // 60)
    assert str(minute) in key


def test_rate_limit_key_default_group():
    """Non-special routes get a 'default' group in the key."""
    config = RateLimitConfig(redis_url="redis://localhost:6379/0")
    from unittest.mock import MagicMock
    app = MagicMock()
    middleware = RateLimiterMiddleware(app, config)

    key = middleware._rate_limit_key("1.2.3.4", "/listings")
    assert "default" in key


# ── Runtime monitor ────────────────────────────────────────────────────────

def test_runtime_monitor_mock_mode():
    """In mock mode, analyze_telemetry never flags abuse."""
    from services.security_service.runtime_monitor import analyze_telemetry

    # Even a perfect xmrig profile passes in mock mode
    payload = {
        "instance_id": "test-123",
        "processes": ["xmrig"],
        "gpu_hash_rate": 9_999_999_999.0,
        "cpu_percent": 100.0,
        "gpu_percent": 0.0,
    }
    report = analyze_telemetry(payload)
    assert report["mining_detected"] is False
    assert report["severity"] == "info"


def test_runtime_monitor_process_detection():
    """Real mode: xmrig in process list → mining detected."""
    from services.security_service.runtime_monitor import MiningDetectedError, analyze_telemetry
    from unittest.mock import patch

    payload = {
        "instance_id": "test-456",
        "processes": ["python3", "xmrig"],
        "gpu_hash_rate": 0.0,
        "cpu_percent": 95.0,
        "gpu_percent": 5.0,
        "network_bytes_out": 0,
    }
    with patch("services.security_service.runtime_monitor.settings") as ms:
        ms.scanner_mock = False
        ms.mining_process_keywords = ["xmrig", "cgminer"]
        ms.mining_suspected_hashrate_threshold = 1_000_000.0

        with pytest.raises(MiningDetectedError) as exc:
            analyze_telemetry(payload)

    assert exc.value.instance_id == "test-456"
    assert any("xmrig" in e for e in exc.value.evidence)


def test_runtime_monitor_clean_workload():
    """Clean LLM inference workload → no detection."""
    from services.security_service.runtime_monitor import analyze_telemetry
    from unittest.mock import patch

    payload = {
        "instance_id": "test-789",
        "processes": ["python3", "uvicorn", "torch"],
        "gpu_hash_rate": 0.0,
        "cpu_percent": 40.0,
        "gpu_percent": 85.0,
        "network_bytes_out": 1024 * 1024,  # 1 MB
    }
    with patch("services.security_service.runtime_monitor.settings") as ms:
        ms.scanner_mock = False
        ms.mining_process_keywords = ["xmrig", "cgminer"]
        ms.mining_suspected_hashrate_threshold = 1_000_000.0

        report = analyze_telemetry(payload)

    assert report["mining_detected"] is False
    assert report["abuse_detected"] is False
