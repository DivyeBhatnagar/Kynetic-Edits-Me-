r"""
LoRA / Adapter Parameter Spectral Backdoor Filter.
Performs Singular Value Decomposition (SVD) and power iteration spectral analysis
on low-rank adapter delta matrices (Delta W = B * A) to detect backdoor Trojan implants.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class LoRASpectralReport:
    adapter_id: str
    rank_r: int
    top_singular_value: float
    singular_value_entropy: float
    spectral_norm_ratio: float
    is_backdoor_suspected: bool
    status: str


class LoRASpectralFilter:
    def __init__(self, max_spectral_ratio_threshold: float = 8.5):
        self.ratio_threshold = max_spectral_ratio_threshold

    def power_iteration_top_singular_values(
        self,
        matrix_a: List[List[float]],
        matrix_b: List[List[float]],
        num_singular_values: int = 4,
        iterations: int = 50,
    ) -> List[float]:
        """
        Computes the top singular values of Delta W = B * A using power iteration.
        Matrix B is (d_out x r), Matrix A is (r x d_in).
        """
        d_out = len(matrix_b)
        r = len(matrix_a)
        d_in = len(matrix_a[0])

        singular_values = []
        # Simulate power iteration on low-rank factorization
        # Delta W * v = B * (A * v)
        for val_idx in range(min(num_singular_values, r)):
            v = [1.0 / math.sqrt(d_in)] * d_in

            for _ in range(iterations):
                # 1. t = A * v (r-dim vector)
                t = [sum(matrix_a[i][j] * v[j] for j in range(d_in)) for i in range(r)]
                # 2. u = B * t (d_out-dim vector)
                u = [sum(matrix_b[i][j] * t[j] for j in range(r)) for i in range(d_out)]
                # Normalize u
                norm_u = math.sqrt(sum(x ** 2 for x in u)) or 1e-9
                u = [x / norm_u for x in u]

                # 3. t2 = B^T * u (r-dim vector)
                t2 = [sum(matrix_b[j][i] * u[j] for j in range(d_out)) for i in range(r)]
                # 4. v_next = A^T * t2 (d_in-dim vector)
                v_next = [sum(matrix_a[j][i] * t2[j] for j in range(r)) for i in range(d_in)]
                norm_v = math.sqrt(sum(x ** 2 for x in v_next)) or 1e-9
                v = [x / norm_v for x in v_next]

            # Approximate singular value \sigma = || B * A * v ||
            t_final = [sum(matrix_a[i][j] * v[j] for j in range(d_in)) for i in range(r)]
            u_final = [sum(matrix_b[i][j] * t_final[j] for j in range(r)) for i in range(d_out)]
            sigma = math.sqrt(sum(x ** 2 for x in u_final))
            singular_values.append(sigma)

        return sorted(singular_values, reverse=True)

    def analyze_adapter(
        self,
        adapter_id: str,
        matrix_a: List[List[float]],
        matrix_b: List[List[float]],
    ) -> LoRASpectralReport:
        r"""
        Analyzes spectral distribution of LoRA matrices.
        Backdoor/Trojan weights display an extreme rank-1 outlier where \sigma_1 >> \sigma_2.
        """
        r = len(matrix_a)
        sigmas = self.power_iteration_top_singular_values(matrix_a, matrix_b, num_singular_values=min(r, 4))

        if len(sigmas) < 2 or sigmas[1] < 1e-6:
            spectral_ratio = 1.0
        else:
            spectral_ratio = sigmas[0] / (sigmas[1] + 1e-9)

        # Calculate singular value entropy
        total_sigma = sum(sigmas) or 1.0
        p_dist = [s / total_sigma for s in sigmas if s > 0]
        entropy = -sum(p * math.log2(p) for p in p_dist) if p_dist else 0.0

        is_backdoor = spectral_ratio > self.ratio_threshold
        status = "SPECTRAL_BACKDOOR_ANOMALY_FLAGGED" if is_backdoor else "LORA_SPECTRAL_PROFILE_CLEAN"

        return LoRASpectralReport(
            adapter_id=adapter_id,
            rank_r=r,
            top_singular_value=round(sigmas[0] if sigmas else 0.0, 4),
            singular_value_entropy=round(entropy, 4),
            spectral_norm_ratio=round(spectral_ratio, 4),
            is_backdoor_suspected=is_backdoor,
            status=status,
        )
