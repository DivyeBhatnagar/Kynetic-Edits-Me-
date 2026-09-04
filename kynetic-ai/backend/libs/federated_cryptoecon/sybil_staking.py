"""
Sybil Resistance & Host Identity Staking Graph.
Correlates IP subnets, ASN, KYC identity hashes, and TPM 2.0 AIK public keys
to compute Sybil risk clustering scores and dynamically calculate collateral staking escrows.
"""

import ipaddress
import math
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


@dataclass
class HostIdentityNode:
    host_id: str
    ip_address: str
    asn: int
    kyc_hash: str
    tpm_aik_pub_hash: str
    staked_collateral_usd: float
    reputation_score: float = 1.0
    active_gpu_count: int = 1


class SybilStakingGraph:
    def __init__(self, base_stake_per_gpu: float = 500.0, max_subnet_concentration: float = 0.25):
        self.base_stake = base_stake_per_gpu
        self.max_subnet_concentration = max_subnet_concentration
        self.hosts: Dict[str, HostIdentityNode] = {}
        self.ip_clusters: Dict[str, Set[str]] = {}  # /24 subnet -> {host_ids}
        self.kyc_clusters: Dict[str, Set[str]] = {}  # kyc_hash -> {host_ids}
        self.tpm_clusters: Dict[str, Set[str]] = {}  # tpm_aik -> {host_ids}

    def register_host(self, host: HostIdentityNode) -> Tuple[bool, float, str]:
        """
        Evaluate host registration against the Sybil graph.
        Returns: (approved, required_collateral_usd, reason)
        """
        # Parse /24 subnet
        try:
            ip_obj = ipaddress.ip_network(f"{host.ip_address}/24", strict=False)
            subnet_key = str(ip_obj)
        except ValueError:
            subnet_key = host.ip_address

        # Check duplicate TPM AIK (direct hardware clone attempt)
        if host.tpm_aik_pub_hash in self.tpm_clusters:
            existing = self.tpm_clusters[host.tpm_aik_pub_hash]
            if host.host_id not in existing and len(existing) > 0:
                return False, 0.0, "TPM_AIK_DUPLICATE_IDENTITY_DETECTED"

        # Calculate Sybil Risk Score [0.0 - 1.0]
        risk_score = self.compute_sybil_risk(host, subnet_key)

        # Dynamic stake scaling: base * (1 + 3 * risk_score)^1.5
        required_stake = self.base_stake * host.active_gpu_count * math.pow(1.0 + 3.0 * risk_score, 1.5)

        if host.staked_collateral_usd < required_stake:
            return False, required_stake, f"INSUFFICIENT_COLLATERAL_FOR_SYBIL_RISK_{risk_score:.2f}"

        # Register into clusters
        self.hosts[host.host_id] = host
        self.ip_clusters.setdefault(subnet_key, set()).add(host.host_id)
        self.kyc_clusters.setdefault(host.kyc_hash, set()).add(host.host_id)
        self.tpm_clusters.setdefault(host.tpm_aik_pub_hash, set()).add(host.host_id)

        return True, required_stake, "HOST_STAKING_APPROVED"

    def compute_sybil_risk(self, host: HostIdentityNode, subnet_key: str) -> float:
        """Compute composite risk based on subnet density, KYC multi-tenancy, and cluster variance."""
        total_hosts = max(len(self.hosts), 1)
        subnet_count = len(self.ip_clusters.get(subnet_key, set()))
        kyc_count = len(self.kyc_clusters.get(host.kyc_hash, set()))

        subnet_ratio = subnet_count / total_hosts if total_hosts > 0 else 0.0
        kyc_penalty = min(kyc_count * 0.15, 0.6)
        subnet_penalty = min(subnet_ratio / self.max_subnet_concentration * 0.4, 0.4)

        raw_score = kyc_penalty + subnet_penalty
        return min(max(raw_score, 0.0), 1.0)

    def deregister_host(self, host_id: str) -> None:
        """Cleanly remove host from Sybil clustering state."""
        if host_id in self.hosts:
            host = self.hosts[host_id]
            try:
                ip_obj = ipaddress.ip_network(f"{host.ip_address}/24", strict=False)
                subnet_key = str(ip_obj)
            except ValueError:
                subnet_key = host.ip_address

            self.ip_clusters.get(subnet_key, set()).discard(host_id)
            self.kyc_clusters.get(host.kyc_hash, set()).discard(host_id)
            self.tpm_clusters.get(host.tpm_aik_pub_hash, set()).discard(host_id)
            del self.hosts[host_id]
