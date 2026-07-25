"""
Host Agent — Runtime Abuse Signature Detector & Image Scanner (abuse_detector.py)

Performs pre-execution OCI image safety scanning and runtime cryptomining signature detection (§14).
"""

import re
import structlog

log = structlog.get_logger(__name__)

# Known cryptominer process patterns & stratum protocol signatures
ABUSE_PATTERNS = [
    re.compile(r"xmrig", re.IGNORECASE),
    re.compile(r"ethminer", re.IGNORECASE),
    re.compile(r"cgminer", re.IGNORECASE),
    re.compile(r"stratum\+tcp://", re.IGNORECASE),
]


class HostAbuseDetector:

    @staticmethod
    def scan_image(image_name: str) -> dict:
        """Pre-execution container image safety check."""
        for pattern in ABUSE_PATTERNS:
            if pattern.search(image_name):
                log.warning("abuse_detector.flagged_image", image=image_name)
                return {"safe": False, "reason": f"Flagged image pattern: {image_name}"}
        return {"safe": True, "reason": "Image clean"}

    @staticmethod
    def scan_process_cmdline(cmdline: str) -> bool:
        """Runtime process command-line inspection."""
        for pattern in ABUSE_PATTERNS:
            if pattern.search(cmdline):
                log.error("abuse_detector.cryptominer_detected", cmdline=cmdline)
                return True
        return False
