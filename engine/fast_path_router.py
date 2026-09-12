"""
AetherBFT: Dual-Path Router & Quorum Accumulator
Manages optimistic unanimous fast-path (Q_fast = 3f+1) and coordinates
fallback to 2-phase Quorum Certificate (QC) consensus when conflicts or missing votes occur.
"""

from typing import Dict, List, Optional, Tuple, Set, Any
try:
    from .crypto_verifier import QuorumCertificate, KeyPair, sha256_digest
except (ImportError, ValueError):
    from crypto_verifier import QuorumCertificate, KeyPair, sha256_digest
try:
    from .dependency_context import Transaction, DependencyContextManager
except (ImportError, ValueError):
    from dependency_context import Transaction, DependencyContextManager


class FastPathRouter:
    """
    Directs transactions to the Fast-Path (1 RTT) if dependency-free,
    or falls back to Slow-Path (2 RTT) if conflicts or non-unanimous quorums occur.
    """
    def __init__(self, n_replicas: int, f_faults: int):
        self.n = n_replicas
        self.f = f_faults
        self.q_fast = n_replicas  # Unanimous fast quorum Q_fast = 3f + 1
        self.q_slow = 2 * f_faults + 1  # Standard slow quorum Q_slow = 2f + 1

        self.dep_manager = DependencyContextManager()

        # In-flight vote accumulators: tx_id -> {node_id: sig_hex}
        self.fast_votes: Dict[str, Dict[str, str]] = {}
        self.slow_votes: Dict[str, Dict[str, str]] = {}

        # Metrics
        self.total_routed = 0
        self.fast_path_attempts = 0
        self.fast_path_successes = 0
        self.slow_path_fallbacks = 0

    def evaluate_route(self, tx: Transaction) -> Tuple[str, List[str]]:
        """
        Evaluates whether transaction is eligible for fast path.
        Returns: ('FAST_PATH' | 'SLOW_PATH', dependencies)
        """
        self.total_routed += 1
        is_eligible, deps = self.dep_manager.is_fast_path_eligible(tx)
        if is_eligible:
            self.fast_path_attempts += 1
            self.dep_manager.register_active(tx)
            self.fast_votes[tx.tx_id] = {}
            return "FAST_PATH", deps
        else:
            self.slow_path_fallbacks += 1
            self.dep_manager.register_active(tx)
            self.slow_votes[tx.tx_id] = {}
            return "SLOW_PATH", deps

    def record_vote(
        self,
        tx_id: str,
        node_id: str,
        signature_hex: str,
        is_fast_path: bool
    ) -> Tuple[bool, Optional[QuorumCertificate]]:
        """
        Records a replica vote for tx_id.
        Returns: (is_quorum_reached, QuorumCertificate)
        """
        if is_fast_path:
            if tx_id not in self.fast_votes:
                self.fast_votes[tx_id] = {}
            self.fast_votes[tx_id][node_id] = signature_hex

            # Check unanimous fast quorum (Q_fast = 3f + 1)
            if len(self.fast_votes[tx_id]) >= self.q_fast:
                self.fast_path_successes += 1
                tx = self.dep_manager.active_transactions.get(tx_id)
                digest = tx.digest if tx else sha256_digest(tx_id)
                qc = QuorumCertificate(
                    view=0,
                    sequence=self.total_routed,
                    digest=digest,
                    dependency_context=[],
                    signatures=self.fast_votes.pop(tx_id),
                    is_fast_path=True
                )
                self.dep_manager.finalize(tx_id)
                return True, qc

            return False, None
        else:
            # Slow path quorum accumulator (Q_slow = 2f + 1)
            if tx_id not in self.slow_votes:
                self.slow_votes[tx_id] = {}
            self.slow_votes[tx_id][node_id] = signature_hex

            if len(self.slow_votes[tx_id]) >= self.q_slow:
                tx = self.dep_manager.active_transactions.get(tx_id)
                digest = tx.digest if tx else sha256_digest(tx_id)
                qc = QuorumCertificate(
                    view=0,
                    sequence=self.total_routed,
                    digest=digest,
                    dependency_context=self.dep_manager.compute_dependency_context(tx) if tx else [],
                    signatures=self.slow_votes.pop(tx_id),
                    is_fast_path=False
                )
                self.dep_manager.finalize(tx_id)
                return True, qc

            return False, None

    def trigger_fallback_to_slow(self, tx_id: str) -> bool:
        """
        If fast-path fails to gather unanimous responses within timeout,
        migrates collected votes to slow-path accumulator.
        """
        if tx_id in self.fast_votes:
            votes = self.fast_votes.pop(tx_id)
            self.slow_votes[tx_id] = votes
            self.slow_path_fallbacks += 1
            return True
        return False

    @property
    def fast_path_success_rate(self) -> float:
        """Computes F(C) = N_fast / N_total."""
        if self.total_routed == 0:
            return 1.0
        return float(self.fast_path_successes / self.total_routed)
