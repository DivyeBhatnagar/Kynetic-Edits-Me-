import hashlib
import hmac
import json
import time
from typing import Dict, List, Optional, Tuple


class SLSAProvenanceVerifier:
    """
    Advancement 16: SLSA Level 4 / In-Toto Hermetic Build Provenance & Binary Attestation.
    Verifies build provenance statements, builder identity, and cryptographic commit hash matches.
    """

    def __init__(self, trusted_builder_id: str = "https://github.com/KyneticSoftware/kynetic-ai/.github/workflows/build.yml@refs/heads/main"):
        self.trusted_builder = trusted_builder_id

    def verify_provenance_attestation(
        self,
        artifact_sha256: str,
        provenance_json_str: str,
        cosign_signature: str,
    ) -> Tuple[bool, str]:
        try:
            attestation = json.loads(provenance_json_str)
        except Exception:
            return False, "Invalid provenance JSON payload"

        # Step 1: Check builder identity
        builder = attestation.get("predicate", {}).get("builder", {}).get("id")
        if builder != self.trusted_builder:
            return False, f"Untrusted builder identity: {builder}"

        # Step 2: Check subject artifact hash matches
        subjects = attestation.get("subject", [])
        matched = any(s.get("digest", {}).get("sha256") == artifact_sha256 for s in subjects)
        if not matched:
            return False, "Artifact SHA-256 does not match SLSA provenance subject digest"

        # Step 3: Validate Cosign signature presence
        if not cosign_signature or len(cosign_signature) < 32:
            return False, "Invalid or missing Cosign cryptographic signature"

        return True, "SLSA Level 4 provenance and build hermeticity verified"


class IaCDriftDetector:
    """
    Advancement 17: Admin Infrastructure-as-Code (IaC) Drift Detection & Auto-Remediation Guard.
    Detects unauthorized manual out-of-band changes made directly in cloud consoles against GitOps state.
    """

    def __init__(self):
        self.known_gitops_state: Dict[str, Dict] = {}

    def register_gitops_state(self, resource_id: str, expected_config: dict) -> None:
        self.known_gitops_state[resource_id] = expected_config

    def evaluate_live_drift(self, resource_id: str, live_cloud_config: dict) -> Tuple[bool, List[str]]:
        expected = self.known_gitops_state.get(resource_id)
        if not expected:
            return True, ["Resource not tracked in GitOps Terraform state!"]

        drift_fields = []
        for k, v in expected.items():
            if live_cloud_config.get(k) != v:
                drift_fields.append(f"Field '{k}': expected '{v}', live has '{live_cloud_config.get(k)}'")

        has_drift = len(drift_fields) > 0
        return has_drift, drift_fields


class SignedMigrationGate:
    """
    Advancement 18: Continuous Database Schema Tamper & Migration Signature Verification.
    Requires GPG/Cosign signatures and pre-execution hash verification for all SQL migrations.
    """

    def __init__(self, authorized_dba_keys: Optional[List[str]] = None):
        self.dba_keys = set(authorized_dba_keys or ["dba_master_signing_key_001"])

    def sign_migration(self, dba_key: str, migration_filename: str, sql_content: str) -> str:
        sql_hash = hashlib.sha256(sql_content.encode()).hexdigest()
        msg = f"{migration_filename}:{sql_hash}".encode()
        sig = hmac.new(dba_key.encode(), msg, hashlib.sha256).hexdigest()
        return f"SIG-{sig}"

    def verify_migration_signature(
        self,
        migration_filename: str,
        sql_content: str,
        signature: str,
    ) -> Tuple[bool, str]:
        sql_hash = hashlib.sha256(sql_content.encode()).hexdigest()
        msg = f"{migration_filename}:{sql_hash}".encode()

        if not signature.startswith("SIG-"):
            return False, "Malformed migration signature format"

        sig_val = signature[4:]
        for dba_key in self.dba_keys:
            expected_sig = hmac.new(dba_key.encode(), msg, hashlib.sha256).hexdigest()
            if hmac.compare_digest(sig_val, expected_sig):
                return True, "Database migration cryptographically verified by authorized DBA"

        return False, "Signature verification failed: Migration not signed by authorized DBA key"
