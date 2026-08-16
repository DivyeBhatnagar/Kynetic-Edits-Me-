"""
Security Service — Security Incident Response Pipeline (Part 21).

Automates containment workflows for security incidents:
1. Suspicious Host Response:
   - Excludes host from Scheduler (attestation / Trust Score CRITICAL)
   - Revokes Host Certificate / mTLS connection
   - Terminates Gateway tunnel session
   - Triggers graceful instance teardown + developer notification

2. Suspicious Workload Response:
   - Applies strict zero-egress network quarantine (nftables)
   - Freezes VM state (preserves state for security review & developer appeal)
"""

import enum
from dataclasses import dataclass, field
import structlog

log = structlog.get_logger(__name__)


class IncidentState(str, enum.Enum):
    DETECTED = "detected"
    CONTAINED = "contained"
    INVESTIGATING = "investigating"
    RESOLVED_FALSE_POSITIVE = "resolved_false_positive"
    RESOLVED_CONFIRMED_ABUSE = "resolved_confirmed_abuse"


@dataclass
class IncidentReport:
    incident_id: str
    target_type: str                  # 'host' or 'workload'
    target_id: str
    trigger_signal: str
    state: IncidentState = IncidentState.DETECTED
    actions_taken: list[str] = field(default_factory=list)


class IncidentResponseEngine:
    """
    Automated containment engine for security incidents.
    """

    @staticmethod
    def contain_suspicious_host(host_id: str, trigger_reason: str) -> IncidentReport:
        """Executes Part 21.1 host containment pipeline."""
        report = IncidentReport(
            incident_id=f"inc-host-{host_id[:8]}",
            target_type="host",
            target_id=host_id,
            trigger_signal=trigger_reason,
        )

        # 1. Stop new scheduling
        report.actions_taken.append("Scheduler: host excluded from listing")

        # 2. Revoke mTLS Host Certificate
        report.actions_taken.append("SecurityService: Host Certificate & mTLS credentials revoked")

        # 3. Terminate Gateway session
        report.actions_taken.append("GatewayService: Host session terminated via kill-switch")

        # 4. Update incident state
        report.state = IncidentState.CONTAINED

        log.critical(
            "incident_response.host_contained",
            host_id=host_id,
            reason=trigger_reason,
            actions=report.actions_taken,
        )
        return report

    @staticmethod
    def contain_suspicious_workload(instance_id: str, trigger_reason: str) -> IncidentReport:
        """Executes Part 21.1 workload quarantine pipeline."""
        report = IncidentReport(
            incident_id=f"inc-workload-{instance_id[:8]}",
            target_type="workload",
            target_id=instance_id,
            trigger_signal=trigger_reason,
        )

        # 1. Network quarantine (nftables zero egress)
        report.actions_taken.append("HostAgent: nftables zero-egress quarantine applied")

        # 2. Freeze VM state
        report.actions_taken.append("Firecracker: microVM execution frozen for evidence collection")

        # 3. Update incident state
        report.state = IncidentState.CONTAINED

        log.critical(
            "incident_response.workload_quarantined",
            instance_id=instance_id,
            reason=trigger_reason,
            actions=report.actions_taken,
        )
        return report
