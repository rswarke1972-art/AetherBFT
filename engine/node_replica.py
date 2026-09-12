"""
AetherBFT: Peer Node Replica
Integrates cryptographic verification, Certified Dependency Contexts,
dual-path speculative routing, MVCC state store, and linearizable read views.
"""

import time
from typing import Dict, List, Optional, Tuple, Set, Any
try:
    from .crypto_verifier import KeyPair, QuorumCertificate, ProofOfEquivocation, sha256_digest
except (ImportError, ValueError):
    from crypto_verifier import KeyPair, QuorumCertificate, ProofOfEquivocation, sha256_digest
try:
    from .dependency_context import Transaction, DependencyContextManager
except (ImportError, ValueError):
    from dependency_context import Transaction, DependencyContextManager
try:
    from .mvcc_version_tree import MVCCVersionTree
except (ImportError, ValueError):
    from mvcc_version_tree import MVCCVersionTree
try:
    from .fast_path_router import FastPathRouter
except (ImportError, ValueError):
    from fast_path_router import FastPathRouter
try:
    from .slow_path_consensus import SlowPathConsensus
except (ImportError, ValueError):
    from slow_path_consensus import SlowPathConsensus


class AetherReplica:
    """
    Full BFT Node Replica in the AetherBFT consensus network.
    """
    def __init__(
        self,
        node_id: str,
        n_replicas: int = 4,
        f_faults: int = 1,
        initial_state: Optional[Dict[str, Any]] = None
    ):
        self.node_id = node_id
        self.n = n_replicas
        self.f = f_faults
        self.keypair = KeyPair()

        # Peer public key registry: node_id -> public_hex
        self.peer_public_keys: Dict[str, str] = {self.node_id: self.keypair.public_hex}
        self.quarantined_nodes: Set[str] = set()

        # Engine Modules
        self.mvcc = MVCCVersionTree(initial_state)
        self.router = FastPathRouter(n_replicas, f_faults)
        self.slow_consensus = SlowPathConsensus(node_id, n_replicas, f_faults, self.keypair)

        # Active transaction tracking: tx_id -> Transaction
        self.active_txs: Dict[str, Transaction] = {}
        self.tx_branches: Dict[str, str] = {}  # tx_id -> branch_id

        # Metrics
        self.total_transactions_processed = 0
        self.fast_commits = 0
        self.slow_commits = 0
        self.rollbacks = 0

    def register_peer(self, peer_id: str, public_hex: str):
        """Registers a peer replica's public key."""
        self.peer_public_keys[peer_id] = public_hex

    # 1. Proposal & Speculative Intake
    def submit_transaction(self, tx: Transaction) -> Dict[str, Any]:
        """
        Processes client transaction:
        1. Checks Certified Dependency Context.
        2. Routes to Fast-Path or Slow-Path.
        3. Creates speculative MVCC branch.
        Returns: {route, status: 'TENTATIVE', branch_id, digest}
        """
        if tx.client_id in self.quarantined_nodes:
            return {"status": "REJECTED_QUARANTINED", "error": "Client is quarantined"}

        self.total_transactions_processed += 1
        self.active_txs[tx.tx_id] = tx

        route, deps = self.router.evaluate_route(tx)

        # Speculative execution on ephemeral branch
        branch_id = f"branch_{tx.tx_id}"
        self.mvcc.apply_speculative(
            parent_branch_id="root_0",
            new_branch_id=branch_id,
            deltas=tx.payload
        )
        self.tx_branches[tx.tx_id] = branch_id

        # Vote for self
        sig_self = self.keypair.sign(tx.digest)
        is_fast = (route == "FAST_PATH")
        self.router.record_vote(tx.tx_id, self.node_id, sig_self, is_fast_path=is_fast)

        return {
            "tx_id": tx.tx_id,
            "route": route,
            "status": "TENTATIVE",  # Explicitly tentative, non-linearizable until finalized
            "branch_id": branch_id,
            "digest": tx.digest,
            "dependencies": deps,
            "vote_sig": sig_self
        }

    # 2. Vote Intake & Finalization
    def receive_vote(
        self,
        tx_id: str,
        from_node: str,
        sig_hex: str,
        is_fast_path: bool
    ) -> Tuple[bool, Optional[QuorumCertificate]]:
        """
        Receives replica vote, validates authenticity, and checks quorum finality.
        """
        if from_node in self.quarantined_nodes:
            return False, None

        pub_hex = self.peer_public_keys.get(from_node)
        if not pub_hex:
            return False, None

        tx = self.active_txs.get(tx_id)
        if not tx:
            return False, None

        if not KeyPair.verify(pub_hex, tx.digest, sig_hex):
            return False, None

        reached, qc = self.router.record_vote(tx_id, from_node, sig_hex, is_fast_path)
        if reached and qc is not None:
            # Finalize MVCC branch
            branch_id = self.tx_branches.get(tx_id)
            if branch_id:
                self.mvcc.finalize_branch(branch_id)

            if qc.is_fast_path:
                self.fast_commits += 1
            else:
                self.slow_commits += 1

            return True, qc

        return False, None

    # 3. Byzantine Equivocation & Quarantine
    def report_equivocation(self, poe: ProofOfEquivocation) -> bool:
        """
        Validates Proof of Equivocation and quarantines the offending node.
        """
        if poe.verify(self.peer_public_keys):
            self.quarantined_nodes.add(poe.offending_node)
            return True
        return False

    # 4. Rollback Handler
    def abort_speculative_transaction(self, tx_id: str) -> int:
        """
        Performs logical rollback of an invalid/equivocated speculative branch in O(1).
        """
        branch_id = self.tx_branches.get(tx_id)
        if branch_id:
            invalidated = self.mvcc.logical_rollback(branch_id)
            self.router.dep_manager.rollback(tx_id)
            self.rollbacks += 1
            return invalidated
        return 0

    # 5. Read APIs (Strict Separation)
    def read_linearizable(self, key: str) -> Tuple[bool, Any]:
        """
        Guaranteed linearizable read from canonical FINALIZED_STATE.
        """
        return self.mvcc.get_finalized(key)

    def read_speculative(self, tx_id: str, key: str) -> Tuple[bool, Any, str]:
        """
        Optimistic read from SPECULATIVE_STATE along transaction's branch.
        Returns: (found, value, status='TENTATIVE')
        """
        branch_id = self.tx_branches.get(tx_id, "root_0")
        return self.mvcc.get_speculative(branch_id, key)

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "total_processed": self.total_transactions_processed,
            "fast_commits": self.fast_commits,
            "slow_commits": self.slow_commits,
            "rollbacks": self.rollbacks,
            "fast_path_rate": self.router.fast_path_success_rate,
            "quarantined_peers": list(self.quarantined_nodes)
        }
