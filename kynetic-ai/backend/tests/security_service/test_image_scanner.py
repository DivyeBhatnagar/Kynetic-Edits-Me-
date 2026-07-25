"""
Tests — Image Scanner (mock mode).

All tests operate in mock mode (SCANNER_MOCK=true), which is the CI default.
Ensures the scanner logic, severity comparison, and result schema work correctly
without requiring Trivy to be installed.
"""

import os

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


from services.security_service.image_scanner import (
    ImageScanBlockedError,
    ImageScanResult,
    _severity_gte,
    scan_image,
)


# ── _severity_gte ──────────────────────────────────────────────────────────

def test_severity_gte_critical_above_high():
    assert _severity_gte("CRITICAL", "HIGH") is True


def test_severity_gte_high_above_medium():
    assert _severity_gte("HIGH", "MEDIUM") is True


def test_severity_gte_low_not_above_high():
    assert _severity_gte("LOW", "HIGH") is False


def test_severity_gte_same():
    assert _severity_gte("HIGH", "HIGH") is True


def test_severity_gte_unknown_lowest():
    assert _severity_gte("UNKNOWN", "LOW") is False


# ── Mock scan_image ────────────────────────────────────────────────────────

def test_mock_scan_passes_any_image():
    """In mock mode, every image passes with zero findings."""
    result = scan_image("xmrig/cpuminer:latest")
    assert isinstance(result, ImageScanResult)
    assert result.passed is True
    assert result.blocked is False
    assert result.finding_count == 0
    assert result.mock is True


def test_mock_scan_ubuntu():
    result = scan_image("ubuntu:24.04")
    assert result.passed is True
    assert result.blocked is False


def test_mock_scan_returns_correct_image_name():
    image = "custom-registry.io/myapp:v1.2.3"
    result = scan_image(image)
    assert result.image == image


def test_mock_scan_zero_findings():
    result = scan_image("some/image")
    assert result.critical_count == 0
    assert result.high_count == 0
    assert result.details == []


# ── ImageScanResult schema ─────────────────────────────────────────────────

def test_image_scan_result_serialization():
    result = ImageScanResult(
        image="test:latest",
        passed=True,
        finding_count=0,
        critical_count=0,
        high_count=0,
        blocked=False,
        mock=True,
    )
    d = result.model_dump()
    assert d["passed"] is True
    assert d["blocked"] is False
    assert "details" in d
