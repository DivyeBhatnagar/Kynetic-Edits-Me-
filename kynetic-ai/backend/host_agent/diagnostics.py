"""
Phase 31 — Host Agent Provisioning Diagnostics (host_agent/diagnostics.py)

Captures host-side job performance metrics and failure diagnostics:
  - Total provisioning duration
  - Image pull time
  - Firecracker microVM boot time
  - Volume setup & encryption time
  - Stack traces on provisioning failures

Structured JSON reports are logged and tagged by `instance_id` to correlate
with control-plane audit logs in `audit_logs`.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

logger = structlog.get_logger("host_agent.diagnostics")


@dataclass
class JobDiagnostics:
    """Diagnostic collector for a single host workload provisioning job."""
    instance_id: str
    host_id: str = "local_host"
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    stage: str = "initialized"
    success: bool = False
    
    # Timing metrics (in milliseconds)
    image_pull_ms: float = 0.0
    volume_setup_ms: float = 0.0
    firecracker_boot_ms: float = 0.0
    total_duration_ms: float = 0.0
    
    # Error diagnostics
    error_message: str | None = None
    error_trace: str | None = None
    extra_context: dict[str, Any] = field(default_factory=dict)

    def record_stage(self, stage_name: str) -> None:
        """Update current provisioning pipeline stage."""
        self.stage = stage_name
        logger.debug(
            "provisioning_stage",
            instance_id=self.instance_id,
            stage=stage_name,
        )

    def record_image_pull(self, duration_sec: float) -> None:
        self.image_pull_ms = round(duration_sec * 1000, 2)

    def record_volume_setup(self, duration_sec: float) -> None:
        self.volume_setup_ms = round(duration_sec * 1000, 2)

    def record_firecracker_boot(self, duration_sec: float) -> None:
        self.firecracker_boot_ms = round(duration_sec * 1000, 2)

    def mark_success(self) -> dict[str, Any]:
        """Finalize timer and export report on success."""
        self.end_time = time.time()
        self.total_duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.stage = "completed"
        self.success = True

        report = self.to_dict()
        logger.info(
            "provisioning_diagnostics.success",
            **report,
        )
        return report

    def mark_failed(self, exception: Exception) -> dict[str, Any]:
        """Finalize timer, capture stack trace, and export report on failure."""
        self.end_time = time.time()
        self.total_duration_ms = round((self.end_time - self.start_time) * 1000, 2)
        self.success = False
        self.error_message = str(exception)
        self.error_trace = traceback.format_exc()

        report = self.to_dict()
        logger.error(
            "provisioning_diagnostics.failure",
            **report,
        )
        return report

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "host_id": self.host_id,
            "stage": self.stage,
            "success": self.success,
            "timing_ms": {
                "total": self.total_duration_ms,
                "image_pull": self.image_pull_ms,
                "volume_setup": self.volume_setup_ms,
                "firecracker_boot": self.firecracker_boot_ms,
            },
            "error": {
                "message": self.error_message,
                "trace": self.error_trace,
            } if self.error_message else None,
            "context": self.extra_context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
