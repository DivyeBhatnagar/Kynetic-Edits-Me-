"""
Phase 14 — Workload Isolation & Security Hardening Tests

Tests:
  - Container & Firecracker MicroVM security profile enforcement
  - Non-root UID execution policy
  - Read-only root filesystem enforcement
  - Forbidden host directory mount prevention
  - Dropped Linux capabilities (cap_drop=['ALL'])
"""

import pytest


def validate_container_security_profile(spec: dict) -> list[str]:
    """
    Audit container launch spec against zero-trust isolation rules.
    Returns list of security violations found.
    """
    violations = []

    # 1. Non-root user check
    user = spec.get("user", "")
    if user in ["root", "0", "0:0", ""]:
        violations.append("Container configured to run as root user")

    # 2. Read-only root filesystem check
    if not spec.get("read_only_rootfs", False):
        violations.append("Root filesystem is not read-only")

    # 3. Cap drop check
    cap_drop = spec.get("cap_drop", [])
    if "ALL" not in cap_drop:
        violations.append("Linux capabilities not dropped with ALL")

    # 4. Host mount security check
    forbidden_mount_paths = ["/", "/etc", "/var", "/proc", "/sys", "/root", "/home"]
    mounts = spec.get("mounts", [])
    for m in mounts:
        host_path = m.get("host_path", "")
        if host_path in forbidden_mount_paths or host_path.startswith("/etc/"):
            violations.append(f"Forbidden host path mounted into container: {host_path}")

    # 5. Privileged mode check
    if spec.get("privileged", False):
        violations.append("Privileged mode is strictly forbidden")

    return violations


class TestWorkloadIsolationSecurity:
    """Security audit tests for workload isolation."""

    def test_compliant_security_profile_has_no_violations(self):
        secure_spec = {
            "user": "1000:1000",
            "read_only_rootfs": True,
            "cap_drop": ["ALL"],
            "privileged": False,
            "mounts": [
                {"host_path": "/var/lib/kynetic/ephemeral/inst-123", "container_path": "/workspace"}
            ]
        }
        violations = validate_container_security_profile(secure_spec)
        assert len(violations) == 0

    def test_root_user_violation_caught(self):
        root_spec = {
            "user": "root",
            "read_only_rootfs": True,
            "cap_drop": ["ALL"],
            "privileged": False,
        }
        violations = validate_container_security_profile(root_spec)
        assert any("run as root" in v for v in violations)

    def test_forbidden_mount_violation_caught(self):
        mount_spec = {
            "user": "1000:1000",
            "read_only_rootfs": True,
            "cap_drop": ["ALL"],
            "privileged": False,
            "mounts": [
                {"host_path": "/etc/shadow", "container_path": "/stolen_shadow"}
            ]
        }
        violations = validate_container_security_profile(mount_spec)
        assert any("Forbidden host path mounted" in v for v in violations)

    def test_privileged_mode_violation_caught(self):
        priv_spec = {
            "user": "1000:1000",
            "read_only_rootfs": True,
            "cap_drop": ["ALL"],
            "privileged": True,
        }
        violations = validate_container_security_profile(priv_spec)
        assert any("Privileged mode is strictly forbidden" in v for v in violations)
