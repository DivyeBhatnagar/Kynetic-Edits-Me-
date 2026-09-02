#!/usr/bin/env python3
"""
Phase 0 — Host Agent Footprint Profiler.

Measures the exact disk footprint of every Kynetic storage component
identified in the optimization plan. Outputs a structured JSON report
suitable for before/after comparison.

Usage:
    python backend/host_agent/scripts/profile_footprint.py
    python backend/host_agent/scripts/profile_footprint.py --json-out /tmp/footprint.json
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


# ── Measured Paths ────────────────────────────────────────────────────────────

MEASURED_PATHS: list[tuple[str, str]] = [
    # (label, path)
    ("agent_binary",               "/opt/kynetic/kynetic-agent"),
    ("vmlinux",                    "/opt/kynetic/vmlinux"),
    ("vmlinux_min",                "/opt/kynetic/vmlinux-min"),
    ("rootfs_ext4",                "/opt/kynetic/rootfs.ext4"),
    ("rootfs_min_ext4",            "/opt/kynetic/rootfs-min.ext4"),
    ("containerd_state",           "/var/lib/containerd"),
    ("docker_state",               "/var/lib/docker"),
    ("kynetic_logs",               "/var/log/kynetic"),
    ("ephemeral_nvme",             "/mnt/kynetic_nvme"),
    ("firecracker_sockets",        "/tmp"),
    ("kynetic_config_dir",         str(Path.home() / ".kynetic_agent")),
    ("wireguard_config",           "/etc/wireguard"),
    ("mtls_certs",                 "/opt/kynetic/certs"),
]

# Python package paths that bloat the venv
PYTHON_PACKAGES: list[tuple[str, str]] = [
    ("torch",     "torch"),
    ("redis",     "redis"),
    ("psutil",    "psutil"),
    ("pynvml",    "pynvml"),
    ("httpx",     "httpx"),
    ("structlog", "structlog"),
]


class PathMeasurement(NamedTuple):
    label: str
    path: str
    exists: bool
    size_bytes: int
    size_human: str


def _size_of(path: str) -> int:
    """Return total size of a path in bytes (recursive for directories)."""
    p = Path(path)
    if not p.exists():
        return 0
    if p.is_file():
        return p.stat().st_size
    total = 0
    for entry in p.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def _human(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} PB"


def measure_paths() -> list[PathMeasurement]:
    results = []
    for label, path in MEASURED_PATHS:
        exists = Path(path).exists()
        size = _size_of(path) if exists else 0
        results.append(PathMeasurement(
            label=label,
            path=path,
            exists=exists,
            size_bytes=size,
            size_human=_human(size),
        ))
    return results


def measure_python_packages() -> dict[str, int]:
    """Find installed package sizes from site-packages."""
    import sysconfig
    site = sysconfig.get_path("purelib")
    sizes: dict[str, int] = {}
    for pkg_label, pkg_dir in PYTHON_PACKAGES:
        pkg_path = os.path.join(site, pkg_dir) if site else ""
        sizes[pkg_label] = _size_of(pkg_path) if pkg_path and Path(pkg_path).exists() else 0
    return sizes


def measure_firecracker_sockets() -> int:
    """Count and size stale Firecracker sockets in /tmp."""
    total = 0
    try:
        for f in Path("/tmp").glob("firecracker-*.sock"):
            try:
                total += f.stat().st_size
            except OSError:
                pass
    except PermissionError:
        pass
    return total


def check_docker_vs_containerd() -> dict:
    info: dict[str, str | bool] = {
        "docker_installed": shutil.which("docker") is not None,
        "containerd_installed": shutil.which("containerd") is not None,
        "stargz_snapshotter_installed": shutil.which("containerd-stargz-grpc") is not None,
        "runc_installed": shutil.which("runc") is not None,
        "firecracker_installed": shutil.which("firecracker") is not None,
    }
    # Docker image layer count and size via docker system df
    if info["docker_installed"]:
        try:
            result = subprocess.run(
                ["docker", "system", "df", "--format", "json"],
                capture_output=True, text=True, timeout=10
            )
            info["docker_df_output"] = result.stdout.strip()
        except Exception as exc:
            info["docker_df_error"] = str(exc)
    return info


def run_profile() -> dict:
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    path_measurements = measure_paths()
    pkg_sizes = measure_python_packages()
    socket_bytes = measure_firecracker_sockets()
    runtime_info = check_docker_vs_containerd()

    total_permanent_bytes = sum(m.size_bytes for m in path_measurements if "nvme" not in m.label and "log" not in m.label)
    total_with_ephemeral = total_permanent_bytes + sum(
        m.size_bytes for m in path_measurements if "nvme" in m.label or "log" in m.label
    )

    report = {
        "timestamp": ts,
        "summary": {
            "permanent_base_bytes": total_permanent_bytes,
            "permanent_base_human": _human(total_permanent_bytes),
            "total_with_ephemeral_bytes": total_with_ephemeral,
            "total_with_ephemeral_human": _human(total_with_ephemeral),
            "stale_sockets_bytes": socket_bytes,
            "stale_sockets_human": _human(socket_bytes),
        },
        "path_measurements": [m._asdict() for m in path_measurements],
        "python_package_sizes": {k: {"size_bytes": v, "size_human": _human(v)} for k, v in pkg_sizes.items()},
        "runtime_environment": runtime_info,
        "optimization_targets": {
            "torch_size_bytes": pkg_sizes.get("torch", 0),
            "redis_size_bytes": pkg_sizes.get("redis", 0),
            "projected_saving_torch_removal_bytes": pkg_sizes.get("torch", 0),
            "projected_saving_redis_removal_bytes": pkg_sizes.get("redis", 0),
        },
    }
    return report


def _print_table(report: dict) -> None:
    summary = report["summary"]
    print("\n" + "═" * 70)
    print("  KYNETIC AI — HOST FOOTPRINT PROFILE")
    print("  Timestamp:", report["timestamp"])
    print("═" * 70)

    print(f"\n{'COMPONENT':<40} {'SIZE':>12}  {'EXISTS':>8}")
    print("-" * 65)
    for m in report["path_measurements"]:
        marker = "✓" if m["exists"] else "✗"
        print(f"  {m['label']:<38} {m['size_human']:>12}  {marker:>8}")

    print(f"\n{'PYTHON PACKAGE':<40} {'SIZE':>12}")
    print("-" * 55)
    for pkg, info in report["python_package_sizes"].items():
        print(f"  {pkg:<38} {info['size_human']:>12}")

    print("\n" + "─" * 70)
    print(f"  Permanent base total:  {summary['permanent_base_human']:>12}")
    print(f"  + Ephemeral total:     {summary['total_with_ephemeral_human']:>12}")
    print(f"  Stale Firecracker sockets: {summary['stale_sockets_human']:>10}")

    targets = report["optimization_targets"]
    print("\n  PROJECTED SAVINGS:")
    print(f"    Remove torch:  -{_human(targets['torch_size_bytes'])}")
    print(f"    Remove redis:  -{_human(targets['redis_size_bytes'])}")
    print("═" * 70 + "\n")


def _human(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes //= 1024
    return f"{size_bytes:.1f} PB"


def main() -> None:
    parser = argparse.ArgumentParser(description="Kynetic Host Agent Footprint Profiler")
    parser.add_argument("--json-out", metavar="PATH", help="Write JSON report to file")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    args = parser.parse_args()

    report = run_profile()

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_table(report)

    if args.json_out:
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2))
        print(f"Report written to: {out_path}")


if __name__ == "__main__":
    main()
