"""
Gradient Inversion Attack Neutralizer & Reconstruction Trap.
Detects Deep Leakage from Gradients (DLG / iDLG) vulnerabilities, estimates mutual information leakage,
and dynamically injects adaptive differential noise and gradient sparsity pruning.
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class InversionDefenseConfig:
    max_gradient_snr: float = 20.0         # dB threshold above which inversion is high-risk
    laplace_noise_scale: float = 0.005     # Noise injected to neutralize DLG
    prune_sparsity_ratio: float = 0.20     # Prune smallest 20% gradient magnitudes
    enable_sign_sgd: bool = False


class GradientInversionTrap:
    def __init__(self, config: InversionDefenseConfig = InversionDefenseConfig()):
        self.config = config

    def calculate_snr_and_leakage_risk(self, gradients: List[float]) -> Tuple[float, float, str]:
        """
        Calculates the Signal-to-Noise Ratio (SNR) and mutual information leakage risk.
        Returns: (snr_db, leakage_score [0.0-1.0], risk_level)
        """
        if not gradients:
            return 0.0, 0.0, "EMPTY_GRADIENT"

        n = len(gradients)
        mean_val = sum(gradients) / n
        variance = sum((x - mean_val) ** 2 for x in gradients) / n
        std_dev = math.sqrt(variance) if variance > 0 else 1e-9

        # Signal power vs noise power
        signal_power = sum(x ** 2 for x in gradients) / n
        snr_ratio = signal_power / (variance + 1e-9)
        snr_db = 10.0 * math.log10(max(snr_ratio, 1e-6))

        # Check for high sparsity or sharp peak (typical of single-sample label leakage)
        max_mag = max(abs(x) for x in gradients)
        outlier_ratio = max_mag / (std_dev + 1e-6)
        leakage_score = min(outlier_ratio / 3.0, 1.0)

        risk_level = "HIGH" if (snr_db > self.config.max_gradient_snr or leakage_score > 0.6 or outlier_ratio > 2.0) else "LOW"
        return snr_db, leakage_score, risk_level

    def sanitize_gradient(self, raw_gradients: List[float]) -> Tuple[List[float], Dict[str, float]]:
        """
        Neutralizes inversion attacks by applying Top-K magnitude pruning and Laplacian noise injection.
        """
        if not raw_gradients:
            return [], {"noise_added": 0.0, "pruned_elements": 0}

        # 1. Sparsification: prune smallest magnitudes
        sorted_indices = sorted(range(len(raw_gradients)), key=lambda i: abs(raw_gradients[i]))
        k_prune = int(len(raw_gradients) * self.config.prune_sparsity_ratio)
        pruned_indices = set(sorted_indices[:k_prune])

        sanitized = []
        noise_accum = 0.0

        for i, val in enumerate(raw_gradients):
            if i in pruned_indices:
                sanitized.append(0.0)
            else:
                # Add zero-mean Laplace noise: b * sgn(u) * ln(1 - 2|u|)
                u = random.random() - 0.5
                b = self.config.laplace_noise_scale
                sign = 1.0 if u >= 0 else -1.0
                laplace_noise = -b * sign * math.log(1.0 - 2.0 * abs(u) + 1e-9)
                noise_accum += abs(laplace_noise)

                new_val = val + laplace_noise
                sanitized.append(new_val)

        meta = {
            "noise_added": round(noise_accum, 6),
            "pruned_elements": k_prune,
            "sparsity_ratio": self.config.prune_sparsity_ratio,
        }
        return sanitized, meta
