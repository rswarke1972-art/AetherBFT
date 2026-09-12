"""
AetherBFT Baseline: Reference Raft (Ongaro & Ousterhout, 2014)
Crash-fault tolerant leader-based consensus.
Used strictly as a non-Byzantine performance reference ceiling (NOT a competing BFT protocol).
"""

from typing import Dict, List, Optional, Tuple, Set, Any


class ReferenceRaftReplica:
    """
    Simulates standard leader-based 1-RTT AppendEntries acknowledgement in crash-fault models.
    Tolerates f < n/2 crash failures (cannot survive Byzantine equivocation).
    """
    def __init__(self, node_id: str, n_nodes: int = 3):
        self.node_id = node_id
        self.n = n_nodes
        self.majority = (n_nodes // 2) + 1

        self.term = 1
        self.log: List[Dict[str, Any]] = []
        self.commit_index = 0
        self.state: Dict[str, Any] = {}

    def append_entries(self, term: int, entries: List[Dict[str, Any]], leader_commit: int) -> bool:
        """Appends log entries from leader."""
        if term < self.term:
            return False

        self.log.extend(entries)
        if leader_commit > self.commit_index:
            new_commit = min(leader_commit, len(self.log))
            for i in range(self.commit_index, new_commit):
                self.state.update(self.log[i].get("payload", {}))
            self.commit_index = new_commit

        return True
