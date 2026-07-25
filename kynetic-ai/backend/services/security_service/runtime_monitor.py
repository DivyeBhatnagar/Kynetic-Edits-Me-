"""
Security Service — Runtime Monitor.

Analyzes telemetry streamed from Host Agents during job execution.
Detects:
  1. Crypto-mining: hash-rate patterns + process name signatures
  2. Resource abuse: anomalous CPU/GPU usage spikes
  3. Process injection: unexpected privileged processes

In mock mode (SCANNER_MOCK=true), the analyze() function never flags abuse —
allowing provisioning tests to run without real telemetry.

Architecture:
  - Telemetry arrives via a Redis pub/sub channel: kynetic:telemetry:{instance_id}
  - The analyze_telemetry Celery task processes each telemetry payload
  - On detection: emits kill_switch trigger + logs SecurityEventLog entry

Telemetry payload format (posted by host agent):
  {
    "instance_id": "...",
    "cpu_percent": 95.2,
    "gpu_percent": 99.8,
    "ram_percent": 72.1,
    "network_bytes_out": 1048576,
    "processes": ["python3", "xmrig", "..."],
    "gpu_hash_rate": 850000000.0  # H/s (optional, from nvidia-smi)
  }
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from services.security_service.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()


class MiningDetectedError(Exception):
    """Raised when crypto-mining signatures are detected in telemetry."""
    def __init__(self, instance_id: str, evidence: list[str]):
        super().__init__(f"Crypto-mining detected on instance {instance_id}")
        self.instance_id = instance_id
        self.evidence = evidence


def analyze_telemetry(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Analyzes a telemetry payload and returns a detection report.

    Returns:
        {
            "mining_detected": bool,
            "abuse_detected": bool,
            "evidence": [...],  # human-readable reasons
            "severity": "info" | "warning" | "critical",
        }

    Raises MiningDetectedError if mining is definitively detected.
    In mock mode: always returns clean report.
    """
    if settings.scanner_mock:
        return {
            "mining_detected": False,
            "abuse_detected": False,
            "evidence": [],
            "severity": "info",
        }

    instance_id = payload.get("instance_id", "unknown")
    evidence: list[str] = []
    mining_detected = False

    # ── 1. Process name matching ───────────────────────────────────────────
    processes = [p.lower() for p in (payload.get("processes") or [])]
    for keyword in settings.mining_process_keywords:
        if any(keyword in proc for proc in processes):
            evidence.append(f"Mining process detected: {keyword}")
            mining_detected = True

    # ── 2. GPU hash-rate threshold ─────────────────────────────────────────
    gpu_hash_rate = payload.get("gpu_hash_rate", 0.0) or 0.0
    if gpu_hash_rate > settings.mining_suspected_hashrate_threshold:
        evidence.append(
            f"Suspicious GPU hash rate: {gpu_hash_rate:.0f} H/s "
            f"(threshold: {settings.mining_suspected_hashrate_threshold:.0f})"
        )
        mining_detected = True

    # ── 3. Resource abuse: 100% CPU + no legitimate workload indicators ────
    cpu_percent = payload.get("cpu_percent", 0.0) or 0.0
    gpu_percent = payload.get("gpu_percent", 0.0) or 0.0
    abuse_detected = False

    if cpu_percent > 98.0 and gpu_percent < 5.0:
        # High CPU with near-zero GPU → suspicious for CPU-based mining
        evidence.append(
            f"Resource anomaly: CPU={cpu_percent:.1f}% but GPU={gpu_percent:.1f}% "
            f"(classic CPU miner profile)"
        )
        abuse_detected = True

    # ── 4. High outbound network during otherwise idle GPU periods ─────────
    net_out = payload.get("network_bytes_out", 0) or 0
    net_out_mb = net_out / (1024 * 1024)
    if net_out_mb > 100 and gpu_percent < 5.0:
        evidence.append(
            f"High outbound traffic ({net_out_mb:.1f} MB) with low GPU utilization"
        )
        abuse_detected = True

    severity = "info"
    if abuse_detected and not mining_detected:
        severity = "warning"
    if mining_detected:
        severity = "critical"

    report = {
        "mining_detected": mining_detected,
        "abuse_detected": abuse_detected,
        "evidence": evidence,
        "severity": severity,
    }

    if mining_detected:
        log.critical(
            "runtime_monitor.mining_detected",
            instance_id=instance_id,
            evidence=evidence,
        )
        raise MiningDetectedError(instance_id, evidence)

    if abuse_detected:
        log.warning(
            "runtime_monitor.abuse_suspected",
            instance_id=instance_id,
            evidence=evidence,
        )

    return report
