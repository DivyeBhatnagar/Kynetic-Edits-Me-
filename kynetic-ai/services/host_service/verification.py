"""
Host Service — Hardware Verification Engine.

Implements Security Pillar 3 MVP tier: cross-checks agent-reported specs
against a maintained table of known GPU hardware signatures to detect
grossly spoofed or misrepresented hardware claims.

Design:
- Known GPU specs are a static lookup table (dict) — Phase 2 seed data.
  In Phase 8, this expands to a ML-assisted detection layer.
- Flagging is conservative: only flag if the mismatch is outside tolerance.
  False positives (flagging legitimate hardware) are worse than false negatives
  at MVP stage because they block legitimate hosts from earning.
"""

import structlog

from services.host_service.schemas import HardwareSpecSchema

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Known GPU Signature Table (MVP seed data)
# ---------------------------------------------------------------------------
# Format: { normalized_gpu_name: { "vram_gb": float, "architecture": str } }
# GPU names are normalized to lowercase, no punctuation.
# Tolerance for VRAM mismatches is configurable (default 10%).
# ---------------------------------------------------------------------------
KNOWN_GPU_SIGNATURES: dict[str, dict] = {
    # NVIDIA Consumer
    "nvidia geforce rtx 4090": {"vram_gb": 24.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4080 super": {"vram_gb": 16.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4080": {"vram_gb": 16.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4070 ti super": {"vram_gb": 16.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4070 ti": {"vram_gb": 12.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4070 super": {"vram_gb": 12.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4070": {"vram_gb": 12.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4060 ti": {"vram_gb": 8.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 4060": {"vram_gb": 8.0, "architecture": "ada_lovelace"},
    "nvidia geforce rtx 3090 ti": {"vram_gb": 24.0, "architecture": "ampere"},
    "nvidia geforce rtx 3090": {"vram_gb": 24.0, "architecture": "ampere"},
    "nvidia geforce rtx 3080 ti": {"vram_gb": 12.0, "architecture": "ampere"},
    "nvidia geforce rtx 3080": {"vram_gb": 10.0, "architecture": "ampere"},
    "nvidia geforce rtx 3070 ti": {"vram_gb": 8.0, "architecture": "ampere"},
    "nvidia geforce rtx 3070": {"vram_gb": 8.0, "architecture": "ampere"},
    "nvidia geforce rtx 3060 ti": {"vram_gb": 8.0, "architecture": "ampere"},
    "nvidia geforce rtx 3060": {"vram_gb": 12.0, "architecture": "ampere"},
    # NVIDIA Data Center
    "nvidia a100": {"vram_gb": 80.0, "architecture": "ampere"},
    "nvidia h100": {"vram_gb": 80.0, "architecture": "hopper"},
    "nvidia h200": {"vram_gb": 141.0, "architecture": "hopper"},
    "nvidia a40": {"vram_gb": 48.0, "architecture": "ampere"},
    "nvidia a10": {"vram_gb": 24.0, "architecture": "ampere"},
    "nvidia rtx a6000": {"vram_gb": 48.0, "architecture": "ampere"},
    "nvidia rtx a4000": {"vram_gb": 16.0, "architecture": "ampere"},
    "nvidia rtx 4000 ada": {"vram_gb": 20.0, "architecture": "ada_lovelace"},
    "nvidia l40s": {"vram_gb": 48.0, "architecture": "ada_lovelace"},
    "nvidia l40": {"vram_gb": 48.0, "architecture": "ada_lovelace"},
    "nvidia l4": {"vram_gb": 24.0, "architecture": "ada_lovelace"},
    # AMD Consumer
    "amd radeon rx 7900 xtx": {"vram_gb": 24.0, "architecture": "rdna3"},
    "amd radeon rx 7900 xt": {"vram_gb": 20.0, "architecture": "rdna3"},
    "amd radeon rx 7800 xt": {"vram_gb": 16.0, "architecture": "rdna3"},
    "amd radeon rx 6800 xt": {"vram_gb": 16.0, "architecture": "rdna2"},
    "amd radeon rx 6700 xt": {"vram_gb": 12.0, "architecture": "rdna2"},
    # Apple Silicon (MPS)
    "apple m2 ultra": {"vram_gb": 192.0, "architecture": "apple_silicon"},
    "apple m2 max": {"vram_gb": 96.0, "architecture": "apple_silicon"},
    "apple m2 pro": {"vram_gb": 32.0, "architecture": "apple_silicon"},
    "apple m3 max": {"vram_gb": 128.0, "architecture": "apple_silicon"},
    "apple m4 max": {"vram_gb": 128.0, "architecture": "apple_silicon"},
}


def _normalize_gpu_name(name: str) -> str:
    """Lowercase, strip extra spaces — used for dict lookup."""
    return " ".join(name.lower().split())


def _fuzzy_match_gpu(reported_name: str) -> str | None:
    """
    Try exact then substring match on known signatures.
    Returns the best-matching key or None.
    """
    normalized = _normalize_gpu_name(reported_name)
    if normalized in KNOWN_GPU_SIGNATURES:
        return normalized
    # Substring match: find the longest known name that is a substring
    best_match = None
    best_len = 0
    for known_name in KNOWN_GPU_SIGNATURES:
        if known_name in normalized and len(known_name) > best_len:
            best_match = known_name
            best_len = len(known_name)
    return best_match


class VerificationResult:
    def __init__(self) -> None:
        self.passed: bool = True
        self.flags: list[str] = []
        self.warnings: list[str] = []

    def flag(self, reason: str) -> None:
        self.passed = False
        self.flags.append(reason)

    def warn(self, reason: str) -> None:
        self.warnings.append(reason)


def verify_hardware_spec(
    spec: HardwareSpecSchema,
    vram_tolerance_pct: float = 10.0,
) -> VerificationResult:
    """
    Cross-check reported hardware against known GPU signatures.

    Checks:
    1. GPU model is in the known signatures table (unknown GPU is a warning, not a flag)
    2. Reported VRAM matches known VRAM within tolerance
    3. Basic sanity: RAM ≥ 1 GB, CPU cores ≥ 1, disk ≥ 10 GB

    Returns VerificationResult with passed=False and flags list if flagged.
    """
    result = VerificationResult()

    # ── Sanity checks ────────────────────────────────────────────────────────
    if spec.ram_gb < 1.0:
        result.flag(f"Implausible RAM: {spec.ram_gb} GB")
    if spec.cpu_cores < 1:
        result.flag(f"Implausible CPU core count: {spec.cpu_cores}")
    if spec.disk_gb < 10.0:
        result.flag(f"Implausible disk size: {spec.disk_gb} GB")

    # ── GPU spec cross-check ─────────────────────────────────────────────────
    if spec.gpu_model and spec.gpu_count > 0:
        matched_key = _fuzzy_match_gpu(spec.gpu_model)
        if matched_key is None:
            # Unknown GPU — warn but don't flag. Could be a new model not in our table.
            result.warn(f"GPU model '{spec.gpu_model}' not in known signatures table — manual review recommended")
            logger.warning(
                "gpu_not_in_signatures",
                gpu_model=spec.gpu_model,
                action="warn_not_flag",
            )
        else:
            known = KNOWN_GPU_SIGNATURES[matched_key]
            expected_vram = known["vram_gb"]

            if spec.gpu_vram_gb is not None:
                # Allow for dual-GPU configs: vram may be total or per-GPU
                # Use per-GPU if gpu_count > 1 and reported value > single-card known spec
                effective_reported = spec.gpu_vram_gb
                if spec.gpu_count > 1 and spec.gpu_vram_gb > expected_vram * 1.5:
                    effective_reported = spec.gpu_vram_gb / spec.gpu_count

                delta_pct = abs(effective_reported - expected_vram) / expected_vram * 100
                if delta_pct > vram_tolerance_pct:
                    result.flag(
                        f"VRAM mismatch: reported {effective_reported:.1f} GB "
                        f"vs expected {expected_vram:.1f} GB for '{matched_key}' "
                        f"(delta {delta_pct:.1f}% > tolerance {vram_tolerance_pct}%)"
                    )
                    logger.warning(
                        "gpu_vram_mismatch",
                        reported_gpu=spec.gpu_model,
                        matched_gpu=matched_key,
                        reported_vram=effective_reported,
                        expected_vram=expected_vram,
                        delta_pct=delta_pct,
                    )
    elif spec.gpu_count > 0 and not spec.gpu_model:
        result.flag("GPU count > 0 but no GPU model reported")

    logger.info(
        "hardware_verification_complete",
        passed=result.passed,
        flags=result.flags,
        warnings=result.warnings,
        gpu_model=spec.gpu_model,
    )
    return result
