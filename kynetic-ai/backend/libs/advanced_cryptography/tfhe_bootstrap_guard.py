"""
Threshold Fully Homomorphic Encryption (TFHE) Bootstrapping Circuit Guard.
Monitors Learning-With-Errors (LWE) ciphertext noise budgets, tracks multiplicative depth,
and coordinates programmable bootstrapping circuits with distributed noise refresh keys.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class CiphertextNoiseBudget:
    ciphertext_id: str
    lwe_dimension: int = 1024
    initial_noise_var: float = 1e-6
    current_noise_var: float = 1e-6
    max_tolerated_noise_var: float = 0.05  # Beyond this threshold, LWE decryption fails
    multiplication_depth: int = 0
    bootstrappings_performed: int = 0
    last_bootstrapped_at: float = field(default_factory=time.time)


class TFHEBootstrapGuard:
    def __init__(self, bootstrap_threshold_ratio: float = 0.70):
        self.bootstrap_threshold_ratio = bootstrap_threshold_ratio
        self.tracked_ciphertexts: Dict[str, CiphertextNoiseBudget] = {}

    def register_ciphertext(self, ct_id: str, lwe_dim: int = 1024) -> CiphertextNoiseBudget:
        budget = CiphertextNoiseBudget(ciphertext_id=ct_id, lwe_dimension=lwe_dim)
        self.tracked_ciphertexts[ct_id] = budget
        return budget

    def record_homomorphic_addition(self, ct_id1: str, ct_id2: str, result_ct_id: str) -> Tuple[bool, CiphertextNoiseBudget]:
        """Homomorphic addition: noise variance adds linearly (Var(e_1 + e_2) = Var(e_1) + Var(e_2))."""
        b1 = self.tracked_ciphertexts.get(ct_id1, CiphertextNoiseBudget(ciphertext_id=ct_id1))
        b2 = self.tracked_ciphertexts.get(ct_id2, CiphertextNoiseBudget(ciphertext_id=ct_id2))

        new_var = b1.current_noise_var + b2.current_noise_var
        new_depth = max(b1.multiplication_depth, b2.multiplication_depth)

        result_budget = CiphertextNoiseBudget(
            ciphertext_id=result_ct_id,
            lwe_dimension=b1.lwe_dimension,
            current_noise_var=new_var,
            multiplication_depth=new_depth,
            bootstrappings_performed=b1.bootstrappings_performed + b2.bootstrappings_performed,
        )
        self.tracked_ciphertexts[result_ct_id] = result_budget

        needs_bootstrap = new_var >= (self.bootstrap_threshold_ratio * result_budget.max_tolerated_noise_var)
        return needs_bootstrap, result_budget

    def record_homomorphic_multiplication(self, ct_id1: str, ct_id2: str, result_ct_id: str) -> Tuple[bool, CiphertextNoiseBudget]:
        """Homomorphic multiplication: noise variance increases quadratically."""
        b1 = self.tracked_ciphertexts.get(ct_id1, CiphertextNoiseBudget(ciphertext_id=ct_id1))
        b2 = self.tracked_ciphertexts.get(ct_id2, CiphertextNoiseBudget(ciphertext_id=ct_id2))

        # Quadratic noise growth: \sigma_{mult}^2 \approx b1.var * b2.var * LWE_dim * 10
        new_var = (b1.current_noise_var * b2.current_noise_var * b1.lwe_dimension * 10.0) + 1e-4
        new_depth = max(b1.multiplication_depth, b2.multiplication_depth) + 1

        result_budget = CiphertextNoiseBudget(
            ciphertext_id=result_ct_id,
            lwe_dimension=b1.lwe_dimension,
            current_noise_var=new_var,
            multiplication_depth=new_depth,
            bootstrappings_performed=b1.bootstrappings_performed + b2.bootstrappings_performed,
        )
        self.tracked_ciphertexts[result_ct_id] = result_budget

        needs_bootstrap = new_var >= (self.bootstrap_threshold_ratio * result_budget.max_tolerated_noise_var)
        return needs_bootstrap, result_budget

    def execute_bootstrapping_circuit(self, ct_id: str) -> Tuple[bool, float, str]:
        """
        Executes TFHE programmable bootstrapping to refresh noise variance back to base noise floor.
        """
        if ct_id not in self.tracked_ciphertexts:
            return False, 0.0, "UNKNOWN_CIPHERTEXT"

        budget = self.tracked_ciphertexts[ct_id]
        if budget.current_noise_var > budget.max_tolerated_noise_var:
            return False, budget.current_noise_var, "CIPHERTEXT_NOISE_CORRUPTED_BEFORE_BOOTSTRAP"

        # Refresh noise to nominal baseline
        budget.current_noise_var = budget.initial_noise_var * 2.0
        budget.bootstrappings_performed += 1
        budget.last_bootstrapped_at = time.time()

        return True, budget.current_noise_var, "BOOTSTRAPPING_REFRESH_SUCCESSFUL"
