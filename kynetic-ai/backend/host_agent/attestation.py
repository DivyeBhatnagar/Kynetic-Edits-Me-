"""
Host Agent — TPM 2.0 Attestation & AIK Module (Part 5).

Generates hardware-rooted PCR quotes signed by the host's Attestation Identity Key (AIK)
in response to a single-use challenge nonce from the Kynetic Attestation Verifier.
"""

import hashlib
import json
import os
import secrets
import structlog

log = structlog.get_logger(__name__)

TPM_MOCK = os.environ.get("TPM_MOCK", "true").lower() == "true"


class TPMAttestationClient:
    """
    Client interface for TPM 2.0 quotation and AIK enrolment.
    """

    def __init__(self, host_id_str: str):
        self.host_id_str = host_id_str

    def generate_quote(self, nonce: str) -> dict:
        """
        Requests the TPM 2.0 chip to quote current PCR measurements signed by the AIK.
        Includes the challenge nonce for replay protection.
        """
        log.info(
            "attestation_client.generate_quote",
            host_id=self.host_id_str,
            nonce=nonce,
            mock=TPM_MOCK,
        )

        if TPM_MOCK:
            pcr_payload = f"MOCK_PCR_DIGEST_{self.host_id_str}_SECUREBOOT_ENABLED"
            pcr_digest = hashlib.sha256(pcr_payload.encode()).hexdigest()
            quote_payload = json.dumps({
                "host_id": self.host_id_str,
                "nonce": nonce,
                "pcr_digest": pcr_digest,
                "secure_boot": True,
                "measured_boot": True,
                "mock": True,
            })
            signature = hashlib.sha256(f"{quote_payload}_AIK_MOCK_SECRET".encode()).hexdigest()
            return {
                "nonce": nonce,
                "pcr_digest": pcr_digest,
                "quote_signature": f"AIK_SIG_{signature}",
                "aik_public_key": f"AIK_PUB_MOCK_{self.host_id_str[:8]}",
                "secure_boot_enabled": True,
                "measured_boot_compliant": True,
            }

        # Production path: invoke tpm2-tools (e.g. tpm2_quote)
        # In real Linux environment with TPM 2.0 chip
        raise NotImplementedError("Hardware TPM 2.0 tpm2-tools integration requires Linux with /dev/tpmrm0")
