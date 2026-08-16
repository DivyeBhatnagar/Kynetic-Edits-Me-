"""
Security Service — Docker Image Scanner.

Wraps the Trivy CLI to scan container images for CVEs before execution.
In mock mode (SCANNER_MOCK=true), all images pass with zero findings —
allowing full integration testing without Trivy installed.

Production flow:
  1. Provisioning service calls scan_image() before starting the container
  2. If any finding at or above SCAN_BLOCK_SEVERITY, raise ImageScanBlockedError
  3. A SecurityEventLog entry is written for every scan (pass or fail)

Trivy is the industry standard open-source scanner (Aqua Security, Apache-2.0).
We invoke it in JSON output mode for structured finding parsing.
"""

import json
import subprocess
import uuid
from typing import Any

import structlog

from services.security_service.config import get_settings
from services.security_service.schemas import ImageScanResult

log = structlog.get_logger(__name__)
settings = get_settings()

# Severity levels in ascending order (matches Trivy's ordering)
SEVERITY_ORDER = ["UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"]


class ImageScanBlockedError(Exception):
    """Raised when an image has findings that exceed the block severity threshold."""
    def __init__(self, image: str, critical: int, high: int):
        super().__init__(
            f"Image '{image}' blocked: {critical} CRITICAL + {high} HIGH findings"
        )
        self.image = image
        self.critical = critical
        self.high = high


def _severity_gte(a: str, b: str) -> bool:
    """Returns True if severity a is >= severity b."""
    try:
        return SEVERITY_ORDER.index(a) >= SEVERITY_ORDER.index(b)
    except ValueError:
        return False


def scan_image(image: str) -> ImageScanResult:
    """
    Scans a Docker image for CVEs using Trivy.

    Returns an ImageScanResult. If blocked=True, the caller MUST NOT start
    the container and MUST raise ImageScanBlockedError.

    In mock mode: returns a clean pass result immediately.
    """
    if settings.scanner_mock:
        log.info("image_scanner.mock_pass", image=image)
        return ImageScanResult(
            image=image,
            passed=True,
            finding_count=0,
            critical_count=0,
            high_count=0,
            blocked=False,
            details=[],
            mock=True,
        )

    log.info("image_scanner.scanning", image=image)
    try:
        result = subprocess.run(
            [
                settings.trivy_binary,
                "image",
                "--format", "json",
                "--exit-code", "0",  # Never let Trivy's exit code mask our logic
                "--no-progress",
                "--quiet",
                image,
            ],
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout
        )
        output = json.loads(result.stdout or "{}")
    except subprocess.TimeoutExpired:
        log.error("image_scanner.timeout", image=image)
        # Conservative: treat timeout as blocked
        return ImageScanResult(
            image=image,
            passed=False,
            finding_count=0,
            critical_count=0,
            high_count=0,
            blocked=True,
            details=[{"error": "scan_timeout"}],
        )
    except Exception as exc:
        log.error("image_scanner.failed", image=image, error=str(exc))
        return ImageScanResult(
            image=image,
            passed=False,
            finding_count=0,
            critical_count=0,
            high_count=0,
            blocked=True,
            details=[{"error": str(exc)}],
        )

    # Parse Trivy JSON output
    findings = []
    critical_count = 0
    high_count = 0
    for target in output.get("Results", []):
        for vuln in target.get("Vulnerabilities") or []:
            sev = vuln.get("Severity", "UNKNOWN")
            findings.append({
                "id": vuln.get("VulnerabilityID"),
                "severity": sev,
                "package": vuln.get("PkgName"),
                "installed_version": vuln.get("InstalledVersion"),
                "fixed_version": vuln.get("FixedVersion"),
                "title": vuln.get("Title"),
            })
            if sev == "CRITICAL":
                critical_count += 1
            elif sev == "HIGH":
                high_count += 1

    blocked = _severity_gte(
        "CRITICAL" if critical_count > 0 else ("HIGH" if high_count > 0 else "LOW"),
        settings.scan_block_severity,
    ) and (critical_count > 0 or high_count > 0)

    result = ImageScanResult(
        image=image,
        passed=not blocked,
        finding_count=len(findings),
        critical_count=critical_count,
        high_count=high_count,
        blocked=blocked,
        details=findings[:100],  # Cap at 100 findings in response
    )

    log.info(
        "image_scanner.complete",
        image=image,
        blocked=blocked,
        critical=critical_count,
        high=high_count,
    )
    return result


def verify_image_signature(image_url: str) -> tuple[bool, str]:
    """
    Part 13 — Cosign Sigstore Image Signature Verification.

    Admission Policy:
      - Unsigned image: REJECT (passed=False)
      - Signed image: ALLOW (passed=True)
    """
    if settings.scanner_mock:
        log.info("image_scanner.cosign_mock_signature_valid", image=image_url)
        return True, "Valid Cosign signature verified (mock mode)."

    try:
        res = subprocess.run(
            ["cosign", "verify", "--key", "/etc/kynetic/cosign.pub", image_url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if res.returncode == 0:
            return True, "Valid Cosign signature verified."
        else:
            log.warning("image_scanner.unsigned_image_rejected", image=image_url, stderr=res.stderr)
            return False, f"Image admission rejected: Unsigned or invalid signature ({res.stderr.strip()})"
    except Exception as exc:
        log.error("image_scanner.cosign_verification_error", image=image_url, error=str(exc))
        return False, f"Image admission error: Cosign verification failed ({str(exc)})"
