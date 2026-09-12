"""
AetherBFT: Slow-Path Consensus Engine & Linear Pacemaker
Implements 2-phase Prepare-Commit Quorum Certificate (QC) consensus
with the formal replica locking invariant and O(n) Pacemaker view changes.
"""

from typing import Dict, List, Optional, Tuple, Set, Any
try:
    from .crypto_verifier import QuorumCertificate, KeyPair, sha256_digest
except (ImportError, ValueError):
    from crypto_verifier import QuorumCertificate, KeyPair, sha256_digest


class SlowPathConsensus:
    """
    Coordinated 2-phase Prepare-Commit consensus with High-QC locking invariant
    and linear O(n) Pacemaker view-change mechanism.
    """
    def __init__(self, node_id: str, n_replicas: int, f_faults: int, keypair: KeyPair):
        self.node_id = node_id
        self.n = n_replicas
        self.f = f_faults
        self.q_size = 2 * f_faults + 1  # Standard BFT Quorum Q = 2f + 1
        self.keypair = keypair

        # Current view & sequence state
        self.current_view = 0
        self.highest_prepared_qc: Optional[QuorumCertificate] = None
        self.locked_qc: Optional[QuorumCertificate] = None

        # Lock / Voting Registry: (view, sequence) -> digest signed
        self.signed_slots: Dict[Tuple[int, int], str] = {}

        # View-Change message buffer: view -> {node_id: (HighQC, sig)}
        self.view_change_votes: Dict[int, Dict[str, Tuple[Optional[QuorumCertificate], str]]] = {}

    def get_leader(self, view: int) -> int:
        """Deterministic round-robin leader selection for view v."""
        return view % self.n

    def is_leader(self, view: int, node_idx: int) -> bool:
        return self.get_leader(view) == node_idx

    def can_sign_proposal(self, view: int, sequence: int, digest: str, high_qc: Optional[QuorumCertificate]) -> bool:
        """
        Formal Replica Signing & Locking Invariant:
        1. Signs at most one value for a given (view, sequence).
        2. Rejects any proposal whose dependency/view is older than current locked_qc.
        """
        slot = (view, sequence)
        if slot in self.signed_slots:
            if self.signed_slots[slot] != digest:
                return False  # Double-signing prevention

        # Check safety rule against locked QC
        if self.locked_qc is not None:
            if high_qc is None or high_qc.view < self.locked_qc.view:
                # Locked value takes precedence unless proposal carries higher QC
                if self.locked_qc.digest != digest:
                    return False

        return True

    def sign_prepare(self, view: int, sequence: int, digest: str, high_qc: Optional[QuorumCertificate]) -> Optional[str]:
        """Signs a Prepare vote if compliant with locking invariants."""
        if not self.can_sign_proposal(view, sequence, digest, high_qc):
            return None

        slot = (view, sequence)
        self.signed_slots[slot] = digest

        msg = sha256_digest({"v": view, "s": sequence, "h": digest, "phase": "PREPARE"})
        return self.keypair.sign(msg)

    def lock_qc(self, qc: QuorumCertificate):
        """Updates replica lock state upon receiving verified Prepare-QC."""
        self.highest_prepared_qc = qc
        self.locked_qc = qc

    def start_view_change(self, next_view: int) -> Tuple[int, Optional[QuorumCertificate], str]:
        """
        Linear Pacemaker: Emits VIEW_CHANGE(v+1, HighQC, signature).
        Communication complexity: O(n) per view change.
        """
        self.current_view = next_view
        msg = sha256_digest({
            "v": next_view,
            "high_qc_view": self.highest_prepared_qc.view if self.highest_prepared_qc else -1,
            "node": self.node_id
        })
        sig = self.keypair.sign(msg)
        return next_view, self.highest_prepared_qc, sig

    def process_view_change_vote(
        self,
        from_node: str,
        view: int,
        high_qc: Optional[QuorumCertificate],
        sig: str,
        peer_public_keys: Dict[str, str]
    ) -> Tuple[bool, Optional[QuorumCertificate]]:
        """
        Leader aggregates O(n) view change messages and preserves highest committed/prepared QC.
        Returns: (has_quorum, best_high_qc)
        """
        pub_hex = peer_public_keys.get(from_node)
        if not pub_hex:
            return False, None

        msg = sha256_digest({
            "v": view,
            "high_qc_view": high_qc.view if high_qc else -1,
            "node": from_node
        })
        if not KeyPair.verify(pub_hex, msg, sig):
            return False, None

        if view not in self.view_change_votes:
            self.view_change_votes[view] = {}

        self.view_change_votes[view][from_node] = (high_qc, sig)

        if len(self.view_change_votes[view]) >= self.q_size:
            # Select High-QC with maximum view among quorum
            best_qc = None
            max_v = -1
            for h_qc, _ in self.view_change_votes[view].values():
                if h_qc is not None and h_qc.view > max_v:
                    max_v = h_qc.view
                    best_qc = h_qc

            return True, best_qc

        return False, None
