"""
Security Plan v5 — Hardened Cryptographic Staging & Anti-Intrusion Fortress Tests

Tests:
  - Security Plan v5 master documentation presence and key sections
  - SecureRAMBuffer ChaCha20-Poly1305 encryption & decryption
  - Anti-tamper prctl dumpable protection & process integrity
  - TPMAttestationEngine PCR quote generation, HMAC verification, and challenge nonces
  - GVisorSandboxPolicy gVisor runsc config and seccomp forbidden syscall filter
  - EBPFNetworkFirewall XDP packet filtering (RFC 1918 drops vs public IP passes)
"""

import os
import pytest

from libs.security.ram_overlay import SecureRAMBuffer
from libs.security.anti_tamper import enforce_anti_debugging_policy, check_process_integrity
from libs.security.tpm_attestation import TPMAttestationEngine
from libs.security.gvisor_sandbox import GVisorSandboxPolicy
from services.security_service.ebpf_firewall import EBPFNetworkFirewall

PLAN_V5_DOC_PATH = os.path.join(
    os.path.dirname(__file__), "../../../Docs/Plans/Kynetic_AI_Zero_Trust_Security_Plan_v5.md"
)


class TestSecurityV5Architecture:
    """Validate Zero-Trust Security Plan v5 Modules."""

    def test_security_v5_doc_exists(self):
        assert os.path.exists(PLAN_V5_DOC_PATH), f"Security Plan v5 doc missing at {PLAN_V5_DOC_PATH}"
        with open(PLAN_V5_DOC_PATH) as f:
            content = f.read()
        assert "Security Plan v5" in content
        for term in ["ChaCha20-Poly1305", "gVisor", "PR_SET_DUMPABLE", "eBPF XDP", "TPM 2.0 PCR"]:
            assert term in content, f"Doc missing term: {term}"

    def test_ram_overlay_chacha20_encryption(self):
        buf = SecureRAMBuffer()
        secret_data = b"developer-sensitive-model-weights-and-prompt-context-12345"

        ciphertext = buf.encrypt_buffer(secret_data)
        assert ciphertext != secret_data
        assert len(ciphertext) == len(secret_data) + 12 + 16  # 12-byte nonce + 16-byte tag

        decrypted = buf.decrypt_buffer(ciphertext)
        assert decrypted == secret_data

    def test_anti_tamper_dumpable_policy(self):
        res = enforce_anti_debugging_policy()
        assert res["dumpable"] is False
        assert res["ptrace_blocked"] is True
        assert check_process_integrity() is True

    def test_tpm_attestation_pcr_quote(self):
        engine = TPMAttestationEngine(host_uuid="host_rtx4090_001")
        nonce = engine.generate_attestation_challenge()
        pcr_hash = "f4c988912e77b61"

        sig = engine.generate_pcr_quote_signature(pcr_hash, nonce)

        # 1. Clean verification
        res1 = engine.verify_attestation_quote(pcr_hash, nonce, sig, expected_pcr_hash=pcr_hash)
        assert res1["valid"] is True

        # 2. Tampered PCR hash -> Fails
        res2 = engine.verify_attestation_quote("tampered_hash_999", nonce, sig, expected_pcr_hash=pcr_hash)
        assert res2["valid"] is False

        # 3. Replayed nonce / bad signature -> Fails
        res3 = engine.verify_attestation_quote(pcr_hash, "old_nonce_replayed", sig, expected_pcr_hash=pcr_hash)
        assert res3["valid"] is False

    def test_gvisor_sandbox_policy(self):
        cfg = GVisorSandboxPolicy.generate_gvisor_config("c_99812")
        assert cfg["runtime"] == "runsc"
        assert cfg["seccomp"]["defaultAction"] == "SCMP_ACT_ERRNO"
        assert GVisorSandboxPolicy.is_syscall_permitted("read") is True
        assert GVisorSandboxPolicy.is_syscall_permitted("ptrace") is False
        assert GVisorSandboxPolicy.is_syscall_permitted("process_vm_readv") is False

    def test_ebpf_firewall_rfc1918_filter(self):
        # 1. Private home Wi-Fi IP -> Dropped
        res1 = EBPFNetworkFirewall.evaluate_outbound_packet("192.168.1.1", 80)
        assert res1["action"] == "XDP_DROP"
        assert res1["allowed"] is False

        # 2. Private 10.x.x.x IP -> Dropped
        res2 = EBPFNetworkFirewall.evaluate_outbound_packet("10.0.0.5", 443)
        assert res2["action"] == "XDP_DROP"

        # 3. Public API IP -> Allowed
        res3 = EBPFNetworkFirewall.evaluate_outbound_packet("8.8.8.8", 443)
        assert res3["action"] == "XDP_PASS"
        assert res3["allowed"] is True
