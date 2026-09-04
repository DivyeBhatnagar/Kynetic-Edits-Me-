"""
Byzantine-Robust Federated Poisoning Filter.
Implements Multi-Krum, Bulyan, and Coordinate-wise Trimmed Median aggregation
to guarantee convergence and prevent backdoor/poisoning attacks from up to f Byzantine colluding workers.
"""

import math
from typing import Dict, List, Tuple


class ByzantineRobustAggregator:
    def __init__(self, byzantine_fault_tolerance_f: int = 1):
        self.f = byzantine_fault_tolerance_f

    def euclidean_distance_sq(self, v1: List[float], v2: List[float]) -> float:
        """Compute squared Euclidean distance between two gradient vectors."""
        return sum((a - b) ** 2 for a, b in zip(v1, v2))

    def multi_krum_aggregate(
        self,
        client_updates: Dict[str, List[float]],
        m_selected: int = 1,
    ) -> Tuple[List[float], List[str]]:
        """
        Multi-Krum aggregation algorithm.
        Selects m_selected vectors that minimize the sum of distances to their n - f - 2 closest neighbors.
        """
        client_ids = list(client_updates.keys())
        n = len(client_ids)

        if n <= 2 * self.f + 2:
            # Fallback to coordinate-wise median if n is too small for Krum condition
            return self.coordinate_wise_median(list(client_updates.values())), client_ids

        # Compute pairwise distance matrix
        distances: Dict[str, Dict[str, float]] = {c: {} for c in client_ids}
        for i, c1 in enumerate(client_ids):
            for c2 in client_ids[i + 1:]:
                dist = self.euclidean_distance_sq(client_updates[c1], client_updates[c2])
                distances[c1][c2] = dist
                distances[c2][c1] = dist

        # Score each client
        k_neighbors = n - self.f - 2
        scores: Dict[str, float] = {}
        for c1 in client_ids:
            sorted_dists = sorted(distances[c1].values())
            scores[c1] = sum(sorted_dists[:k_neighbors])

        # Pick the top m_selected clients with lowest Krum scores
        selected_clients = sorted(scores.keys(), key=lambda c: scores[c])[:m_selected]

        # Average the selected vectors
        dim = len(client_updates[selected_clients[0]])
        aggregated = [0.0] * dim
        for c in selected_clients:
            vec = client_updates[c]
            for i in range(dim):
                aggregated[i] += vec[i]

        aggregated = [val / len(selected_clients) for val in aggregated]
        return aggregated, selected_clients

    def coordinate_wise_median(self, vectors: List[List[float]]) -> List[float]:
        """Compute coordinate-wise median across all worker updates."""
        if not vectors:
            return []
        dim = len(vectors[0])
        result = []
        for i in range(dim):
            coords = sorted(vec[i] for vec in vectors)
            mid = len(coords) // 2
            if len(coords) % 2 == 1:
                result.append(coords[mid])
            else:
                result.append((coords[mid - 1] + coords[mid]) / 2.0)
        return result

    def bulyan_aggregate(self, client_updates: Dict[str, List[float]]) -> Tuple[List[float], List[str]]:
        """
        Bulyan aggregation: combines Multi-Krum selection with coordinate-wise trimmed mean
        to provide optimal defense against both directional and scale-shifting Byzantine attacks.
        """
        client_ids = list(client_updates.keys())
        n = len(client_ids)
        if n < 4 * self.f + 3:
            return self.multi_krum_aggregate(client_updates, m_selected=max(1, n - 2 * self.f))

        # 1. Selection step: Use Krum iteratively to pick theta = n - 2*f candidates
        theta = n - 2 * self.f
        _, selected_subset = self.multi_krum_aggregate(client_updates, m_selected=theta)

        selected_vectors = [client_updates[c] for c in selected_subset]
        dim = len(selected_vectors[0])
        bulyan_vector = []

        # 2. Coordinate-wise trimmed mean on the selected subset
        # Remove top f and bottom f extremes for each coordinate
        for i in range(dim):
            coords = sorted(vec[i] for vec in selected_vectors)
            trimmed = coords[self.f : len(coords) - self.f]
            bulyan_vector.append(sum(trimmed) / len(trimmed))

        return bulyan_vector, selected_subset
