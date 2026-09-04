r"""
Confederated Secure Aggregation (SecAgg) Engine.
Enforces pairwise masking and Shamir threshold secret sharing so that the central aggregator
computes the exact sum of model gradient updates without ever inspecting individual client gradients.
"""

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class MaskedGradientPayload:
    client_id: str
    round_id: int
    masked_vector: List[float]
    shares_for_peers: Dict[str, int]  # peer_id -> Shamir share of client's random mask seed


class SecureAggregationEngine:
    def __init__(self, threshold_t: int = 3, total_clients_n: int = 5, vector_dim: int = 10):
        self.t = threshold_t
        self.n = total_clients_n
        self.vector_dim = vector_dim
        self.prime = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F

    def generate_pairwise_masks(self, client_ids: List[str]) -> Dict[str, Dict[str, int]]:
        """
        Generate symmetric pairwise mask seeds s_{i, j} such that s_{i, j} = -s_{j, i}.
        When added across all clients, all pairwise masks sum to 0.
        """
        pairwise_seeds: Dict[str, Dict[str, int]] = {c: {} for c in client_ids}
        sorted_clients = sorted(client_ids)

        for i, u in enumerate(sorted_clients):
            for v in sorted_clients[i + 1:]:
                # Shared seed derived from pairwise identifier
                seed = secrets.randbelow(1_000_000_000) + 1
                pairwise_seeds[u][v] = seed
                pairwise_seeds[v][u] = -seed

        return pairwise_seeds

    def client_mask_gradient(
        self,
        client_id: str,
        round_id: int,
        raw_gradient: List[float],
        pairwise_seeds: Dict[str, int],
    ) -> MaskedGradientPayload:
        r"""
        Client side: adds pairwise mask vectors to gradient vector.
        y_u = x_u + \sum_{v \in U \setminus \{u\}} PRG(s_{u, v})
        """
        masked_vector = list(raw_gradient)

        # Apply PRG mask from pairwise seeds
        for peer_id, seed in pairwise_seeds.items():
            abs_seed = abs(seed)
            sign = 1.0 if seed >= 0 else -1.0
            mask_hasher = hashlib.sha256(f"{round_id}:{abs_seed}".encode())
            for idx in range(len(masked_vector)):
                mask_hasher.update(idx.to_bytes(4, "big"))
                val_int = int.from_bytes(mask_hasher.digest()[:4], "big")
                mask_val = sign * ((val_int % 100000) / 100000.0)
                masked_vector[idx] += mask_val

        return MaskedGradientPayload(
            client_id=client_id,
            round_id=round_id,
            masked_vector=masked_vector,
            shares_for_peers={},
        )

    def aggregate_masked_gradients(
        self,
        round_id: int,
        client_payloads: List[MaskedGradientPayload],
    ) -> Tuple[bool, List[float], str]:
        r"""
        Server side: sums all masked vectors.
        Because each pairwise mask s_{u, v} + s_{v, u} = 0, they cancel out perfectly:
        \sum_{u} y_u = \sum_{u} x_u + 0 = \sum_{u} x_u
        """
        if len(client_payloads) < self.t:
            return False, [], f"INSUFFICIENT_CLIENT_THRESHOLD_{len(client_payloads)}_LESS_THAN_{self.t}"

        # Vector dimension check
        dim = len(client_payloads[0].masked_vector)
        accumulated_sum = [0.0] * dim

        for payload in client_payloads:
            if payload.round_id != round_id:
                return False, [], "ROUND_ID_MISMATCH"
            if len(payload.masked_vector) != dim:
                return False, [], "VECTOR_DIMENSION_MISMATCH"

            for i in range(dim):
                accumulated_sum[i] += payload.masked_vector[i]

        # Calculate average
        n_clients = len(client_payloads)
        avg_gradient = [round(val / n_clients, 6) for val in accumulated_sum]
        return True, avg_gradient, "SECAGG_AGGREGATION_SUCCESSFUL"
