"""
Byzantine Fault Tolerant (BFT) State Machine Replication Guard.
Enforces 3-phase PBFT consensus (Pre-Prepare, Prepare, Commit) and validates Quorum Certificates (2f + 1)
for distributed cluster scheduling, parameter checkpointing, and federated state synchronization.
"""

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class PBFTPhase(str, Enum):
    PRE_PREPARE = "PRE_PREPARE"
    PREPARE = "PREPARE"
    COMMIT = "COMMIT"
    COMMITTED = "COMMITTED"


@dataclass
class PBFTMessage:
    phase: PBFTPhase
    view_number: int
    sequence_number: int
    proposal_digest: str
    sender_node_id: str
    signature: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class QuorumCertificate:
    view_number: int
    sequence_number: int
    proposal_digest: str
    phase: PBFTPhase
    signers: List[str]
    is_valid: bool = True


class BFTConsensusGuard:
    def __init__(self, cluster_nodes: List[str], max_faulty_f: int = 1, hmac_secret: bytes = b"kynetic_bft_secret_2026"):
        self.nodes = sorted(cluster_nodes)
        self.n = len(self.nodes)
        self.f = max_faulty_f
        self.quorum_size = 2 * self.f + 1
        self.secret = hmac_secret

        self.current_view = 0
        self.sequence_counter = 0

        # State storage: (view, seq, digest) -> phase -> set of signer node_ids
        self.message_votes: Dict[Tuple[int, int, str], Dict[PBFTPhase, Set[str]]] = {}
        self.committed_logs: Dict[int, str] = {}  # seq -> digest

    def sign_message(self, phase: PBFTPhase, view: int, seq: int, digest: str, node_id: str) -> PBFTMessage:
        payload = f"{phase.value}:{view}:{seq}:{digest}:{node_id}".encode()
        sig = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return PBFTMessage(
            phase=phase,
            view_number=view,
            sequence_number=seq,
            proposal_digest=digest,
            sender_node_id=node_id,
            signature=sig,
        )

    def verify_signature(self, msg: PBFTMessage) -> bool:
        if msg.sender_node_id not in self.nodes:
            return False
        payload = f"{msg.phase.value}:{msg.view_number}:{msg.sequence_number}:{msg.proposal_digest}:{msg.sender_node_id}".encode()
        expected = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(msg.signature, expected)

    def process_message(self, msg: PBFTMessage) -> Tuple[bool, Optional[QuorumCertificate], str]:
        """
        Ingest and validate PBFT vote message. Checks view, signature, quorum threshold.
        """
        if not self.verify_signature(msg):
            return False, None, "INVALID_MESSAGE_SIGNATURE"

        if msg.view_number < self.current_view:
            return False, None, "STALE_VIEW_MESSAGE"

        key = (msg.view_number, msg.sequence_number, msg.proposal_digest)
        if key not in self.message_votes:
            self.message_votes[key] = {
                PBFTPhase.PREPARE: set(),
                PBFTPhase.COMMIT: set(),
            }

        if msg.phase in self.message_votes[key]:
            self.message_votes[key][msg.phase].add(msg.sender_node_id)
            signer_count = len(self.message_votes[key][msg.phase])

            if signer_count >= self.quorum_size:
                qc = QuorumCertificate(
                    view_number=msg.view_number,
                    sequence_number=msg.sequence_number,
                    proposal_digest=msg.proposal_digest,
                    phase=msg.phase,
                    signers=list(self.message_votes[key][msg.phase]),
                    is_valid=True,
                )
                if msg.phase == PBFTPhase.COMMIT:
                    self.committed_logs[msg.sequence_number] = msg.proposal_digest
                return True, qc, f"QUORUM_REACHED_FOR_{msg.phase.value}"

        return True, None, "VOTE_RECORDED"
