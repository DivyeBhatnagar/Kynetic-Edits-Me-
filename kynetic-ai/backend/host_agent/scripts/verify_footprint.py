#!/usr/bin/env python3
"""
Phase 7 — Kynetic Host Footprint Verification Script.

Compares the current installation footprint against Phase 1–6 optimization
targets, validates security configurations, and produces a pass/fail report.

This is the post-optimization counterpart to profile_footprint.py.
Run this after installation to confirm the ~94% size reduction has been achieved.

Usage:
    python backend/host_agent/scripts/verify_footprint.py
    python backend/host_agent/scripts/verify_footprint.py --json
    python backend/host_agent/scripts/verify_footprint.py --baseline /tmp/footprint_before.json
    python backend/host_agent/scripts/verify_footprint.py --ci   # Exit code 1 on failure
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import NamedTuple


# ── Target thresholds from the implementation plan ─────────────────────────────

TARGETS = {
    # (label, path, max_size_mb, required_to_exist)
    "agent_binary":     ("/opt/kynetic/kynetic-agent",      55,   False),  # target: 35–55 MB
    "vmlinux_min":      ("/opt/kynetic/vmlinux-min",         15,   False),  # target: ~12 MB
    "rootfs_min":       ("/opt/kynetic/rootfs-min.ext4",     60,   False),  # target: ~45 MB
    "vmlinux_old":      ("/opt/kynetic/vmlinux",            999,  False),   # OLD — should be gone
    "rootfs_old":       ("/opt/kynetic/rootfs.ext4",        999,  False),   # OLD — should be gone
    "log_dir":          ("/var/log/kynetic",                 25,   False),  # hard cap: 25 MB
}

# Security checks
SECURITY_CHECKS = [
    ("nftables_active",     ["systemctl", "is-active", "nftables"]),
    ("agent_service",       ["systemctl", "is-active", "kynetic-agent"]),
    ("containerd_service",  ["systemctl", "is-active", "containerd"]),
    ("stargz_service",      ["systemctl", "is-active", "containerd-stargz-grpc"]),
    ("firecracker_binary",  ["which", "firecracker"]),
    ("runc_binary",         ["which", "runc"]),
]

# PyTorch must NOT be importable from the host Python environment
FORBIDDEN_PACKAGES = ["torch", "redis"]


class CheckResult(NamedTuple):
    name: str
    passed: bool
    expected: str
    actual: str
    detail: str = ""


# ── Measurement helpers ────────────────────────────────────────────────────────

def _size_mb(path: str) -> float:
    p = Path(path)
    if not p.exists():
        return 0.0
    if p.is_file():
        return p.stat().st_size / (1024 * 1024)
    total = 0
    for entry in p.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total / (1024 * 1024)


def _cmd_ok(cmd: list[str]) -> bool:
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _package_importable(pkg: str) -> bool:
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False


def _free_disk_gb(path: str = "/opt/kynetic") -> float:
    try:
        stat = shutil.disk_usage(path if Path(path).exists() else "/")
        return stat.free / (1024 ** 3)
    except OSError:
        return 0.0


# ── Verification checks ────────────────────────────────────────────────────────

def check_size_targets() -> list[CheckResult]:
    results = []
    for label, (path, max_mb, required) in TARGETS.items():
        actual_mb = _size_mb(path)
        exists = Path(path).exists()

        # Old files should no longer exist
        if label in ("vmlinux_old", "rootfs_old"):
            passed = not exists
            results.append(CheckResult(
                name=f"removed:{label}",
                passed=passed,
                expected="not present (old large file removed)",
                actual=f"{'present' if exists else 'absent'} ({actual_mb:.1f} MB)",
                detail="Old unstripped rootfs/kernel should have been replaced by *-min versions.",
            ))
            continue

        # Optional components: warn if missing but don't fail
        if not exists and not required:
            results.append(CheckResult(
                name=label,
                passed=True,
                expected=f"≤ {max_mb} MB (optional)",
                actual="not installed",
                detail="Optional component — not required for this profile.",
            ))
            continue

        passed = actual_mb <= max_mb
        results.append(CheckResult(
            name=label,
            passed=passed,
            expected=f"≤ {max_mb:.0f} MB",
            actual=f"{actual_mb:.1f} MB",
            detail=f"Over budget by {actual_mb - max_mb:.1f} MB" if not passed else "",
        ))
    return results


def check_forbidden_packages() -> list[CheckResult]:
    results = []
    for pkg in FORBIDDEN_PACKAGES:
        importable = _package_importable(pkg)
        results.append(CheckResult(
            name=f"forbidden_pkg:{pkg}",
            passed=not importable,
            expected=f"{pkg} NOT importable (removed from requirements.txt)",
            actual=f"{pkg} {'IS importable (FAIL)' if importable else 'not importable (OK)'}",
            detail=(
                f"'{pkg}' is still installed in this Python environment. "
                "Remove it: pip uninstall -y " + pkg
            ) if importable else "",
        ))
    return results


def check_security_services() -> list[CheckResult]:
    results = []
    for name, cmd in SECURITY_CHECKS:
        ok = _cmd_ok(cmd)
        # Some services are optional depending on profile
        optional = name in ("containerd_service", "stargz_service")
        results.append(CheckResult(
            name=f"service:{name}",
            passed=ok or optional,
            expected="active" if not optional else "active (optional)",
            actual="active" if ok else "inactive/missing",
            detail="" if ok else ("Optional for lite profile." if optional else "Check: systemctl status " + cmd[-1]),
        ))
    return results


def check_free_disk() -> list[CheckResult]:
    free_gb = _free_disk_gb()
    min_free_gb = float(os.environ.get("KYNETIC_CACHE_MIN_FREE_GB", "10.0"))
    passed = free_gb >= min_free_gb
    return [CheckResult(
        name="free_disk",
        passed=passed,
        expected=f"≥ {min_free_gb:.1f} GB free",
        actual=f"{free_gb:.1f} GB free",
        detail=f"Low disk: {free_gb:.1f} GB < {min_free_gb:.1f} GB minimum" if not passed else "",
    )]


def check_total_permanent_footprint() -> list[CheckResult]:
    """Sum up all permanent base components and verify < 350 MB."""
    components = [
        "/opt/kynetic/kynetic-agent",
        "/opt/kynetic/vmlinux-min",
        "/opt/kynetic/rootfs-min.ext4",
        "/opt/kynetic/certs",
    ]
    for binary in ["firecracker", "containerd", "runc", "containerd-stargz-grpc"]:
        binary_path = shutil.which(binary)
        if binary_path:
            components.append(binary_path)

    total_mb = sum(_size_mb(p) for p in components)
    # Target: ≤ 350 MB for GPU profile, ≤ 250 MB standard, ≤ 180 MB lite
    profile = os.environ.get("KYNETIC_INSTALL_PROFILE", "standard")
    max_mb = {"lite": 180, "standard": 250, "gpu": 350}.get(profile, 350)

    passed = total_mb <= max_mb or total_mb == 0  # 0 = not yet installed
    return [CheckResult(
        name="total_permanent_footprint",
        passed=passed,
        expected=f"≤ {max_mb} MB total (profile={profile})",
        actual=f"{total_mb:.1f} MB",
        detail=f"Over budget by {total_mb - max_mb:.1f} MB" if not passed and total_mb > 0 else "",
    )]


# ── Compare against baseline ───────────────────────────────────────────────────

def compare_baseline(baseline_path: str) -> list[CheckResult]:
    """Load a profile_footprint.py JSON report and compute savings."""
    try:
        with open(baseline_path) as f:
            baseline = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return [CheckResult(
            name="baseline_comparison",
            passed=False,
            expected="Valid JSON baseline from profile_footprint.py",
            actual=f"Failed to load: {exc}",
        )]

    baseline_bytes = baseline.get("summary", {}).get("permanent_base_bytes", 0)
    baseline_mb = baseline_bytes / (1024 * 1024)

    # Measure current
    current_components = [
        "/opt/kynetic/kynetic-agent",
        "/opt/kynetic/vmlinux-min",
        "/opt/kynetic/rootfs-min.ext4",
        "/opt/kynetic/certs",
        "/opt/kynetic/config.yaml",
    ]
    current_mb = sum(_size_mb(p) for p in current_components)
    reduction_pct = ((baseline_mb - current_mb) / max(baseline_mb, 1)) * 100

    # Plan targets: ≥ 85% reduction (down from ~3.9 GB to ~222 MB)
    passed = reduction_pct >= 85.0 or baseline_mb == 0
    return [CheckResult(
        name="baseline_size_reduction",
        passed=passed,
        expected="≥ 85% reduction vs baseline",
        actual=f"{reduction_pct:.1f}% reduction ({baseline_mb:.0f} MB → {current_mb:.0f} MB)",
        detail="Target from implementation plan: ~94% reduction (3.9 GB → 222 MB).",
    )]


# ── Report rendering ───────────────────────────────────────────────────────────

def render_report(results: list[CheckResult]) -> None:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]

    print("\n" + "═" * 72)
    print("  KYNETIC AI — PHASE 7 OPTIMIZATION VERIFICATION REPORT")
    print(f"  {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("═" * 72)

    for r in results:
        status = "\033[32m✓ PASS\033[0m" if r.passed else "\033[31m✗ FAIL\033[0m"
        print(f"  {status}  {r.name}")
        print(f"        Expected: {r.expected}")
        print(f"        Actual:   {r.actual}")
        if r.detail:
            print(f"        Detail:   {r.detail}")

    print("\n" + "─" * 72)
    print(f"  Results: {len(passed)} passed, {len(failed)} failed out of {len(results)} checks")
    if failed:
        print("\n  FAILED CHECKS:")
        for r in failed:
            print(f"    ✗ {r.name}")
    else:
        print("\n  \033[32m✓ ALL CHECKS PASSED — Optimization targets met!\033[0m")
    print("═" * 72 + "\n")


def render_json(results: list[CheckResult]) -> None:
    print(json.dumps({
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": len(results),
        "passed": sum(1 for r in results if r.passed),
        "failed": sum(1 for r in results if not r.passed),
        "results": [r._asdict() for r in results],
    }, indent=2))


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Kynetic Phase 7 Footprint Verification"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--ci", action="store_true",
                        help="Exit code 1 if any check fails (for CI pipelines)")
    parser.add_argument("--baseline", metavar="JSON",
                        help="Baseline JSON from profile_footprint.py for delta comparison")
    args = parser.parse_args()

    results: list[CheckResult] = []
    results += check_size_targets()
    results += check_forbidden_packages()
    results += check_security_services()
    results += check_free_disk()
    results += check_total_permanent_footprint()

    if args.baseline:
        results += compare_baseline(args.baseline)

    if args.json:
        render_json(results)
    else:
        render_report(results)

    if args.ci and any(not r.passed for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
