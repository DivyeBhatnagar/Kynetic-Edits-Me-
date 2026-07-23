"""
Security Plan v4 — Zero-Trust Security Infrastructure Tests

Tests:
  - HardwareSecurityReport tier classification logic (Confidential vs Standard tier)
  - AttestationSealer ECDH + HKDF secret sealing and in-enclave unsealing
  - Continuous ReAttestationEngine auto-kill triggers (VFIO unbind, quote hash change)
  - ComputeExecutionCertificateIssuer Ed25519 signing and offline verification
  - Zero-Trust Security Plan v4 documentation presence and structure
"""

import os
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from libs.security.cc_detector import HardwareSecurityReport, inspect_host_security_capabilities
from services.security_service.attestation_sealer import AttestationSealer
from services.security_service.continuous_attestation import ReAttestationEngine
from services.security_service.execution_cert import ComputeExecutionCertificateIssuer

PLAN_V4_DOC_PATH = os.path.join(
    os.path.dirname(__file__), "../../../Docs/Plans/Kynetic_AI_Zero_Trust_Security_Plan_v4.md"
)


class TestSecurityV4Architecture:
    """Validate Zero-Trust Security v4 Modules."""

    def test_security_doc_exists_and_contains_key_pillars(self):
        assert os.path.exists(PLAN_V4_DOC_PATH), f"Security Plan v4 document missing at {PLAN_V4_DOC_PATH}"
        with open(PLAN_V4_DOC_PATH) as f:
            content = f.read()
        assert len(content) > 1000, "Security Plan v4 document is too short"
        for phrase in [
            "Host-Blind Hardware Isolation",
            "Attestation Gateway",
            "Ephemeral LUKS",
            "SEV-SNP",
            "NVIDIA Hopper CC",
            "Execution Certificate",
        ]:
            assert phrase in content, f"Plan v4 doc missing required phrase: {phrase}"

    def test_hardware_security_report_classification(self):
        rep = HardwareSecurityReport()
        assert rep.determined_tier == "standard_tier"

        rep.sev_snp = True
        rep.nvidia_cc = True
        rep.tpm_present = True
        assert rep.determined_tier == "confidential_tier"

    def test_attestation_secret_sealing_unsealing(self):
        # 1. Enclave key pair
        enclave_privkey = ec.generate_private_key(ec.SECP384R1())
        enclave_pubkey_bytes = enclave_privkey.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        secret = b"super-secret-ssh-key-and-model-decryption-key"

        # 2. Control plane seals secret for enclave
        sealed_ciphertext = AttestationSealer.seal_secret_for_enclave(secret, enclave_pubkey_bytes)
        assert len(sealed_ciphertext) > len(secret)
        assert sealed_ciphertext != secret

        # 3. Enclave unseals secret inside hardware memory
        unsealed_secret = AttestationSealer.unseal_secret_in_enclave(sealed_ciphertext, enclave_privkey)
        assert unsealed_secret == secret

    def test_continuous_reattestation_kill_triggers(self):
        engine = ReAttestationEngine(host_id="host_991", job_id="job_882", expected_hash="hash_abc_123")

        # 1. Normal clean attestation
        res1 = engine.verify_live_attestation(live_quote_hash="hash_abc_123", vfio_bound=True)
        assert res1["valid"] is True
        assert res1["action"] == "CONTINUE"

        # 2. Host unbinds GPU from VFIO mid-session -> Auto-kill
        res2 = engine.verify_live_attestation(live_quote_hash="hash_abc_123", vfio_bound=False)
        assert res2["valid"] is False
        assert res2["action"] == "EMERGENCY_KILL"

        # 3. Host measurement hash changed -> Auto-kill
        res3 = engine.verify_live_attestation(live_quote_hash="hash_tampered_999", vfio_bound=True)
        assert res3["valid"] is False
        assert res3["action"] == "EMERGENCY_KILL"

    def test_execution_certificate_issuance_and_verification(self):
        issuer = ComputeExecutionCertificateIssuer()
        cert = issuer.issue_certificate(
            job_id="job_999",
            host_id="host_111",
            security_tier="confidential_tier",
            attestation_passes=120,
        )

        assert cert["issuer"] == "Kynetic Zero-Trust Certification Authority"
        assert issuer.verify_certificate(cert) is True

        # Tampered certificate payload fails verification
        cert["payload"]["attestation_failures"] = 99
        assert issuer.verify_certificate(cert) is False
