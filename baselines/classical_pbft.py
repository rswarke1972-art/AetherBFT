"""
AetherBFT Baseline: Classical PBFT (Castro & Liskov, 1999)
Three-phase consensus (Pre-Prepare -> Prepare -> Commit) with O(n^2) message exchanges.
Used as a classical Byzantine Fault Tolerant comparison baseline.
"""

import time
from typing import Dict, List, Optional, Tuple, Set, Any
import hashlib
import json


class ClassicalPBFTReplica:
    """
    Simulates a classical 3-phase PBFT replica requiring 3 RTT phases:
    1. Pre-Prepare (Leader broadcast)
    2. Prepare (All-to-all broadcast: gathers 2f+1 prepare votes)
    3. Commit (All-to-all broadcast: gathers 2f+1 commit votes)
    """
    def __init__(self, node_id: str, n_nodes: int = 4, f_faults: int = 1):
        self.node_id = node_id
        self.n = n_nodes
        self.f = f_faults
        self.quorum = 2 * f_faults + 1

        self.view = 0
        self.sequence = 0
        self.state: Dict[str, Any] = {}

        # Vote stores: seq -> set of node_ids
        self.prepare_votes: Dict[int, Set[str]] = {}
        self.commit_votes: Dict[int, Set[str]] = {}
        self.committed_seqs: Set[int] = set()

    def process_pre_prepare(self, seq: int, digest: str) -> str:
        """Phase 1: Validates Pre-Prepare and emits Prepare vote."""
        self.sequence = seq
        if seq not in self.prepare_votes:
            self.prepare_votes[seq] = set()
        self.prepare_votes[seq].add(self.node_id)
        return "PREPARE"

    def process_prepare(self, from_node: str, seq: int) -> bool:
        """Phase 2: Collects Prepare votes until 2f+1 reached."""
        if seq not in self.prepare_votes:
            self.prepare_votes[seq] = set()
        self.prepare_votes[seq].add(from_node)

        # Has prepared certificate
        return len(self.prepare_votes[seq]) >= self.quorum

    def process_commit(self, from_node: str, seq: int, payload: Dict[str, Any]) -> bool:
        """Phase 3: Collects Commit votes until 2f+1 reached, then executes."""
        if seq not in self.commit_votes:
            self.commit_votes[seq] = set()
        self.commit_votes[seq].add(from_node)

        if len(self.commit_votes[seq]) >= self.quorum and seq not in self.committed_seqs:
            self.committed_seqs.add(seq)
            self.state.update(payload)
            return True
        return False
