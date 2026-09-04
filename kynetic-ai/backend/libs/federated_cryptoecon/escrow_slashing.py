"""
Automated Escrow Slashing Protocol.
Processes cryptographic proof-of-violation evidence (tampered attestation, canary failures, poisoned updates)
and executes atomic staking slashing, blacklist enforcement, and victim compensation distribution.
"""

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ViolationSeverity(str, Enum):
    MINOR_SLA_DROPOUT = "MINOR_SLA_DROPOUT"       # 10% slash
    REPEATED_CANARY_FAIL = "REPEATED_CANARY_FAIL"   # 35% slash
    TAMPERED_ATTESTATION = "TAMPERED_ATTESTATION"   # 100% slash + permaban
    BYZANTINE_GRADIENT_POISON = "BYZANTINE_GRADIENT_POISON" # 100% slash + permaban
    DMA_IOMMU_ESCAPE_ATTEMPT = "DMA_IOMMU_ESCAPE_ATTEMPT"   # 100% slash + permaban


@dataclass
class ViolationEvidence:
    host_id: str
    severity: ViolationSeverity
    cryptographic_proof_payload: str
    detector_agent_id: str
    timestamp: float = field(default_factory=time.time)
    evidence_hash: str = ""

    def __post_init__(self):
        if not self.evidence_hash:
            data = f"{self.host_id}:{self.severity.value}:{self.cryptographic_proof_payload}:{self.timestamp}"
            self.evidence_hash = hashlib.sha256(data.encode()).hexdigest()


@dataclass
class SlashingReceipt:
    slashing_id: str
    host_id: str
    severity: ViolationSeverity
    amount_slashed_usd: float
    remaining_escrow_usd: float
    burned_amount_usd: float
    insurance_pool_usd: float
    banned: bool
    timestamp: float


class EscrowSlashingProtocol:
    def __init__(self, insurance_pool_fraction: float = 0.5):
        self.insurance_pool_fraction = insurance_pool_fraction
        self.host_escrows: Dict[str, float] = {}
        self.banned_hosts: Dict[str, str] = {}  # host_id -> reason
        self.slashing_history: List[SlashingReceipt] = []

    def set_host_escrow(self, host_id: str, amount_usd: float) -> None:
        self.host_escrows[host_id] = max(amount_usd, 0.0)

    def get_host_escrow(self, host_id: str) -> float:
        return self.host_escrows.get(host_id, 0.0)

    def is_banned(self, host_id: str) -> bool:
        return host_id in self.banned_hosts

    def process_violation(self, evidence: ViolationEvidence) -> Tuple[bool, Optional[SlashingReceipt], str]:
        """
        Evaluate violation evidence and execute atomic escrow slash.
        """
        host_id = evidence.host_id
        if self.is_banned(host_id):
            return False, None, "HOST_ALREADY_BANNED"

        current_escrow = self.host_escrows.get(host_id, 0.0)
        if current_escrow <= 0:
            # Immediate ban if zero escrow
            self.banned_hosts[host_id] = f"ZERO_ESCROW_VIOLATION_{evidence.severity.value}"
            return False, None, "ZERO_ESCROW_HOST_BANNED"

        # Determine slash fraction & ban policy
        if evidence.severity in (ViolationSeverity.TAMPERED_ATTESTATION,
                                 ViolationSeverity.BYZANTINE_GRADIENT_POISON,
                                 ViolationSeverity.DMA_IOMMU_ESCAPE_ATTEMPT):
            slash_fraction = 1.0
            should_ban = True
        elif evidence.severity == ViolationSeverity.REPEATED_CANARY_FAIL:
            slash_fraction = 0.35
            should_ban = False
        else:
            slash_fraction = 0.10
            should_ban = False

        amount_slashed = current_escrow * slash_fraction
        new_escrow = current_escrow - amount_slashed
        self.host_escrows[host_id] = new_escrow

        if should_ban or new_escrow <= 0.01:
            self.banned_hosts[host_id] = f"CRITICAL_VIOLATION_{evidence.severity.value}"

        insurance_alloc = amount_slashed * self.insurance_pool_fraction
        burned_alloc = amount_slashed - insurance_alloc

        receipt = SlashingReceipt(
            slashing_id=f"slash_{evidence.evidence_hash[:16]}",
            host_id=host_id,
            severity=evidence.severity,
            amount_slashed_usd=round(amount_slashed, 2),
            remaining_escrow_usd=round(new_escrow, 2),
            burned_amount_usd=round(burned_alloc, 2),
            insurance_pool_usd=round(insurance_alloc, 2),
            banned=self.is_banned(host_id),
            timestamp=time.time(),
        )

        self.slashing_history.append(receipt)
        return True, receipt, "SLASHING_EXECUTED_SUCCESSFULLY"
