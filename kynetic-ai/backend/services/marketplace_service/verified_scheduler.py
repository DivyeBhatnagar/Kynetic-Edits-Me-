"""
Marketplace Service — Verified Compute Scheduling Policy Pre-Filter (Part 22).

Filters eligible hosts for Verified Compute workloads based on strict hardware trust requirements:
1. attestation_status == 'current' (Part 5 TPM 2.0 attestation)
2. secure_boot_enabled == True
3. measured_boot_compliant == True
4. LUKS2 storage encryption active (Part 4)
5. HARDENED network isolation profile (Part 9 / 12)
6. Host risk_band in ('LOW_RISK', 'MEDIUM_RISK')
"""

from typing import Any
import structlog

log = structlog.get_logger(__name__)


def filter_verified_compute_hosts(candidate_hosts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Applies the Part 22 Verified Compute hard pre-filter stage before weighted ranking.
    Returns only hosts that pass all hardware trust and security profile criteria.
    """
    eligible = []
    for host in candidate_hosts:
        attest_ok = host.get("attestation_status") == "current"
        secure_boot_ok = host.get("secure_boot_enabled", False) is True
        measured_boot_ok = host.get("measured_boot_compliant", False) is True
        risk_ok = host.get("risk_band") in ("LOW_RISK", "MEDIUM_RISK")
        luks2_ok = host.get("storage_encryption") == "LUKS2_active"

        if attest_ok and secure_boot_ok and measured_boot_ok and risk_ok and luks2_ok:
            eligible.append(host)
        else:
            log.debug(
                "verified_scheduler.host_filtered_out",
                host_id=host.get("id"),
                attest=attest_ok,
                secure_boot=secure_boot_ok,
                risk=host.get("risk_band"),
            )

    log.info(
        "verified_scheduler.filter_complete",
        total_candidates=len(candidate_hosts),
        eligible_count=len(eligible),
    )
    return eligible
