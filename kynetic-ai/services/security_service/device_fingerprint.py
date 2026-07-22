"""
Security Service — Device Fingerprint Logic.

The fingerprint is computed on the client side (browser) and posted to the
backend as a SHA-256 hex string.

Client-side signals to include (implemented in the frontend):
  - navigator.userAgent
  - navigator.language
  - screen.width × screen.height × screen.colorDepth
  - navigator.hardwareConcurrency
  - Intl.DateTimeFormat().resolvedOptions().timeZone
  - canvas fingerprint (2D context rendering)

These are hashed client-side before transmission — we never store raw signals.

Backend responsibilities (this module):
  1. Upsert the fingerprint record for this user×hash pair
  2. Count how many distinct users have presented this same hash
  3. If > 1 user → log multi_account_suspected SecurityEventLog entry
"""

import hashlib
import uuid
from typing import Any


def compute_fingerprint(signals: dict[str, Any]) -> str:
    """
    Deterministically hashes a dict of browser signals into a SHA-256 hex string.
    Used in tests to simulate client-side fingerprinting.
    """
    stable = str(sorted(signals.items())).encode("utf-8")
    return hashlib.sha256(stable).hexdigest()
