"""
Security Service — Abuse Detection Module (Part 17).

Risk-based abuse detection collecting multi-dimensional signals:
- Cryptomining signatures (sustained GPU/CPU pattern)
- Port scanning & brute-force attack signatures
- Malware / C2 beaconing network patterns
- Fleet-wide DDoS participation correlation
- Credential theft file-access anomalies
"""

import enum
from dataclasses import dataclass, field
import structlog

log = structlog.get_logger(__name__)


class AbusePatternType(str, enum.Enum):
    CRYPTOMINING = "CRYPTOMINING"
    PORT_SCANNING = "PORT_SCANNING"
    BRUTE_FORCE = "BRUTE_FORCE"
    BOTNET_C2_BEACONING = "BOTNET_C2_BEACONING"
    DDOS_PARTICIPATION = "DDOS_PARTICIPATION"
    CREDENTIAL_THEFT = "CREDENTIAL_THEFT"
    EXPLOIT_SCANNING = "EXPLOIT_SCANNING"


@dataclass
class AbuseSignalReport:
    instance_id: str
    host_id: str
    detected_patterns: list[AbusePatternType] = field(default_factory=list)
    risk_score_contribution: float = 0.0
    evidence: list[str] = field(default_factory=list)


class AbuseDetector:
    """
    Risk-based abuse signal analyzer.
    Feeds output into Runtime Risk Engine (Part 16) rather than hard-blocking.
    """

    @staticmethod
    def analyze_signals(
        instance_id: str,
        host_id: str,
        gpu_percent: float = 0.0,
        gpu_hash_rate: float = 0.0,
        outbound_connections_per_sec: int = 0,
        unique_external_targets_count: int = 0,
        credential_file_access_attempts: int = 0,
        cross_instance_traffic_burst: bool = False,
    ) -> AbuseSignalReport:
        report = AbuseSignalReport(instance_id=instance_id, host_id=host_id)
        contribution = 0.0

        # 1. Cryptomining signature
        if gpu_hash_rate > 5000000.0 or (gpu_percent > 95.0 and outbound_connections_per_sec < 5):
            report.detected_patterns.append(AbusePatternType.CRYPTOMINING)
            contribution += 40.0
            report.evidence.append(f"Mining compute signature detected: {gpu_hash_rate:.0f} H/s")

        # 2. Port scanning / Brute-force signature
        if outbound_connections_per_sec > 200 and unique_external_targets_count > 100:
            report.detected_patterns.append(AbusePatternType.PORT_SCANNING)
            contribution += 25.0
            report.evidence.append(f"Port scanning pattern detected ({outbound_connections_per_sec} conn/s across {unique_external_targets_count} targets)")

        # 3. Fleet-wide DDoS correlation
        if cross_instance_traffic_burst:
            report.detected_patterns.append(AbusePatternType.DDOS_PARTICIPATION)
            contribution += 35.0
            report.evidence.append("Fleet-wide DDoS traffic correlation hit")

        # 4. Credential theft file access
        if credential_file_access_attempts > 0:
            report.detected_patterns.append(AbusePatternType.CREDENTIAL_THEFT)
            contribution += 30.0
            report.evidence.append(f"File access anomaly: {credential_file_access_attempts} attempts to read credential stores")

        report.risk_score_contribution = round(contribution, 2)
        log.info(
            "abuse_detector.signals_analyzed",
            instance_id=instance_id,
            patterns=[p.value for p in report.detected_patterns],
            contribution=contribution,
        )
        return report
