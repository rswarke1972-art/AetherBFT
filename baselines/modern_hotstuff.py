"""
AetherBFT Baseline: Modern Pipelined HotStuff (Yin et al., 2019)
Pipelined 3-chain BFT consensus (Prepare -> Pre-Commit -> Commit) with linear Pacemaker.
Used as a modern Byzantine Fault Tolerant comparison baseline.
"""

from typing import Dict, List, Optional, Tuple, Set, Any
import json
import hashlib


class HotStuffBlock:
    def __init__(self, view: int, payload: Dict[str, Any], parent_hash: str):
        self.view = view
        self.payload = payload
        self.parent_hash = parent_hash
        self.block_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        data = {"v": self.view, "p": self.payload, "parent": self.parent_hash}
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


class ModernHotStuffReplica:
    """
    Simulates a 3-chain pipelined HotStuff replica.
    A block is committed when a 3-chain of certified blocks is formed.
    """
    def __init__(self, node_id: str, n_nodes: int = 4, f_faults: int = 1):
        self.node_id = node_id
        self.n = n_nodes
        self.f = f_faults
        self.quorum = 2 * f_faults + 1

        self.current_view = 0
        self.locked_block: Optional[HotStuffBlock] = None
        self.state: Dict[str, Any] = {}
        self.committed_blocks: List[HotStuffBlock] = []

    def vote_block(self, block: HotStuffBlock) -> bool:
        """Evaluates voting rule: block must extend from locked block or carry higher view."""
        if self.locked_block is not None:
            if block.view <= self.locked_block.view:
                return False
        return True

    def commit_three_chain(self, b_commit: HotStuffBlock, b_precommit: HotStuffBlock, b_prepare: HotStuffBlock):
        """Finalizes block when verified 3-chain extends parent references."""
        if b_prepare.parent_hash == b_precommit.block_hash and b_precommit.parent_hash == b_commit.block_hash:
            self.committed_blocks.append(b_commit)
            self.state.update(b_commit.payload)
            self.locked_block = b_precommit
