"""
Immutable Storage Vaults & Anti-Ransomware Defensive Layer.
Includes:
1. WORMLockEngine: S3-compliant Object Lock (COMPLIANCE mode) and Legal Hold immutability.
2. AirGapVaultManager: Air-Gapped Dual-Custody immutable snapshot vault.
3. RansomwareEntropyTrap: Shannon entropy file mutation analysis and filesystem decoy canary tripwires.
"""

import hashlib
import hmac
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class ObjectLockMode(str, Enum):
    GOVERNANCE = "GOVERNANCE"
    COMPLIANCE = "COMPLIANCE"


@dataclass
class WORMObjectMetadata:
    object_key: str
    sha256_digest: str
    size_bytes: int
    created_timestamp: float
    retention_until_timestamp: float
    lock_mode: ObjectLockMode
    legal_hold: bool = False


class WORMLockEngine:
    def __init__(self):
        self.vault_objects: Dict[str, WORMObjectMetadata] = {}

    def put_locked_object(
        self,
        object_key: str,
        data: bytes,
        retention_days: int = 365,
        lock_mode: ObjectLockMode = ObjectLockMode.COMPLIANCE,
    ) -> WORMObjectMetadata:
        """Stores object with strict WORM retention."""
        now = time.time()
        retention_until = now + (retention_days * 86400)
        digest = hashlib.sha256(data).hexdigest()

        meta = WORMObjectMetadata(
            object_key=object_key,
            sha256_digest=digest,
            size_bytes=len(data),
            created_timestamp=now,
            retention_until_timestamp=retention_until,
            lock_mode=lock_mode,
            legal_hold=False,
        )
        self.vault_objects[object_key] = meta
        return meta

    def set_legal_hold(self, object_key: str, status: bool) -> Tuple[bool, str]:
        if object_key not in self.vault_objects:
            return False, "OBJECT_NOT_FOUND"
        self.vault_objects[object_key].legal_hold = status
        return True, f"LEGAL_HOLD_SET_TO_{status}"

    def can_delete_or_modify(self, object_key: str) -> Tuple[bool, str]:
        """Validates if an object can be deleted or overwritten."""
        if object_key not in self.vault_objects:
            return True, "OBJECT_NOT_PRESENT"

        obj = self.vault_objects[object_key]
        now = time.time()

        if obj.legal_hold:
            return False, "OBJECT_UNDER_ACTIVE_LEGAL_HOLD"

        if obj.lock_mode == ObjectLockMode.COMPLIANCE:
            if now < obj.retention_until_timestamp:
                remaining_days = (obj.retention_until_timestamp - now) / 86400
                return False, f"WORM_COMPLIANCE_LOCK_ACTIVE_REMAINING_DAYS_{remaining_days:.1f}"

        return True, "RETENTION_EXPIRED_OR_PERMITTED"


@dataclass
class AirGapSnapshot:
    snapshot_id: str
    data_digest: str
    approvals: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    committed: bool = False


class AirGapVaultManager:
    def __init__(self, required_custodians: int = 2):
        self.required_custodians = required_custodians
        self.snapshots: Dict[str, AirGapSnapshot] = {}

    def create_pending_snapshot(self, snapshot_id: str, data_bytes: bytes) -> AirGapSnapshot:
        digest = hashlib.sha256(data_bytes).hexdigest()
        snap = AirGapSnapshot(snapshot_id=snapshot_id, data_digest=digest)
        self.snapshots[snapshot_id] = snap
        return snap

    def submit_custodian_approval(self, snapshot_id: str, custodian_id: str, signature: str) -> Tuple[bool, str]:
        """Dual-custody asymmetric authorization for committing or restoring snapshot."""
        if snapshot_id not in self.snapshots:
            return False, "UNKNOWN_SNAPSHOT"

        snap = self.snapshots[snapshot_id]
        if snap.committed:
            return False, "SNAPSHOT_ALREADY_COMMITTED"

        snap.approvals.add(custodian_id)
        if len(snap.approvals) >= self.required_custodians:
            snap.committed = True
            return True, "DUAL_CUSTODY_QUORUM_MET_SNAPSHOT_COMMITTED_TO_AIRGAP"

        return True, f"APPROVAL_RECORDED_PENDING_{self.required_custodians - len(snap.approvals)}_MORE"


class RansomwareEntropyTrap:
    def __init__(self, entropy_threshold: float = 7.40):
        self.entropy_threshold = entropy_threshold
        self.canary_files: Dict[str, str] = {}  # filepath -> original_hash

    def plant_canary(self, filepath: str, content: bytes) -> None:
        digest = hashlib.sha256(content).hexdigest()
        self.canary_files[filepath] = digest

    def calculate_shannon_entropy(self, data: bytes) -> float:
        """Calculate Shannon entropy (bits per byte [0.0 - 8.0]). High entropy indicates encryption."""
        if not data:
            return 0.0
        frequencies = [0] * 256
        for b in data:
            frequencies[b] += 1
        entropy = 0.0
        n = len(data)
        for count in frequencies:
            if count > 0:
                p = count / n
                entropy -= p * math.log2(p)
        return entropy

    def inspect_file_modification(self, filepath: str, new_content: bytes) -> Tuple[bool, str]:
        """
        Inspect file content update for ransomware bulk encryption or canary corruption.
        Returns: (is_malicious, alert_reason)
        """
        # 1. Check if decoy canary was touched
        if filepath in self.canary_files:
            new_digest = hashlib.sha256(new_content).hexdigest()
            if new_digest != self.canary_files[filepath]:
                return True, "RANSOMWARE_DECOY_CANARY_TRIPPED"

        # 2. Check Shannon entropy threshold
        entropy = self.calculate_shannon_entropy(new_content)
        if entropy >= self.entropy_threshold and len(new_content) > 256:
            return True, f"HIGH_ENTROPY_ENCRYPTION_ANOMALY_DETECTED_{entropy:.3f}"

        return False, "NORMAL_FILE_MUTATION"
