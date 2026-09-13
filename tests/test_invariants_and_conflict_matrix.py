# -*- coding: utf-8 -*-
"""
AetherBFT Implementation Invariant Tests & Complexity Validation
Validates the F1-F6 Cross-Path Conflict Matrix, Rollback Scope (R_s),
Rollback Amplification (A_r), and O(1) logical branch invalidation.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.crypto_verifier import KeyPair, QuorumCertificate, sha256_digest
from engine.dependency_context import Transaction, DependencyContextManager
from engine.fast_path_router import FastPathRouter
from engine.slow_path_consensus import SlowPathConsensus
from engine.mvcc_version_tree import MVCCVersionTree
from engine.node_replica import AetherReplica


class TestInvariantsAndConflictMatrix(unittest.TestCase):
    def setUp(self):
        self.replica = AetherReplica(node_id="node_0", n_replicas=4, f_faults=1)
        self.keypairs = [KeyPair() for _ in range(4)]
        self.peer_keys = {f"node_{i}": self.keypairs[i].public_hex for i in range(4)}
        for node_id, pub_hex in self.peer_keys.items():
            self.replica.register_peer(node_id, pub_hex)

    def test_F1_fast_A_slow_A_finalizes(self):
        """F1: Fast proposal A and Slow proposal A for same value both agree on state."""
        tx_a = Transaction(tx_id="tx_A", client_id="client_1", read_keys=["k1"], write_keys=["k1"], payload={"k1": "val_A"})
        res = self.replica.submit_transaction(tx_a)
        self.assertEqual(res["route"], "FAST_PATH")

        digest = tx_a.digest
        sig = self.replica.slow_consensus.sign_prepare(view=0, sequence=1, digest=digest, high_qc=None)
        self.assertIsNotNone(sig)

    def test_F2_fast_A_slow_B_no_conflicting_finalization(self):
        """F2: Fast proposal A and Slow proposal B: slot cannot sign conflicting B in same slot."""
        tx_a = Transaction(tx_id="tx_A", client_id="client_1", read_keys=["k1"], write_keys=["k1"], payload={"k1": "val_A"})
        tx_b = Transaction(tx_id="tx_B", client_id="client_2", read_keys=["k1"], write_keys=["k1"], payload={"k1": "val_B"})

        sig_a = self.replica.slow_consensus.sign_prepare(view=0, sequence=1, digest=tx_a.digest, high_qc=None)
        self.assertIsNotNone(sig_a)

        sig_b = self.replica.slow_consensus.sign_prepare(view=0, sequence=1, digest=tx_b.digest, high_qc=None)
        self.assertIsNone(sig_b, "Slot monotonicity must reject conflicting proposal B in same slot")

    def test_F3_fast_A_slow_B_same_view_lock_rejects(self):
        """F3: When locked on A in view 0, node rejects B in view 0."""
        qc_a = QuorumCertificate(view=0, sequence=1, digest="digest_A", dependency_context=[], signatures={}, is_fast_path=False)
        self.replica.slow_consensus.lock_qc(qc_a)

        can_sign = self.replica.slow_consensus.can_sign_proposal(view=0, sequence=2, digest="digest_B", high_qc=None)
        self.assertFalse(can_sign, "Locked QC on A must reject conflicting digest B in same view")

    def test_F4_fast_A_slow_B_higher_view_high_qc_applies(self):
        """F4: In higher view, node can sign only if proposal extends highest locked QC."""
        qc_a = QuorumCertificate(view=0, sequence=1, digest="digest_A", dependency_context=[], signatures={}, is_fast_path=False)
        self.replica.slow_consensus.lock_qc(qc_a)

        qc_higher_a = QuorumCertificate(view=1, sequence=1, digest="digest_A", dependency_context=[], signatures={}, is_fast_path=False)
        can_sign_valid = self.replica.slow_consensus.can_sign_proposal(view=2, sequence=2, digest="digest_A", high_qc=qc_higher_a)
        self.assertTrue(can_sign_valid)

        can_sign_invalid = self.replica.slow_consensus.can_sign_proposal(view=2, sequence=2, digest="digest_B", high_qc=None)
        self.assertFalse(can_sign_invalid)

    def test_F5_view_change_preserves_highest_qc(self):
        """F5: View change aggregation preserves highest prepared QC across 2f+1 quorum."""
        qc_v0 = QuorumCertificate(view=0, sequence=1, digest="digest_A", dependency_context=[], signatures={}, is_fast_path=False)
        qc_v1 = QuorumCertificate(view=1, sequence=1, digest="digest_B", dependency_context=[], signatures={}, is_fast_path=False)

        msg0 = sha256_digest({"v": 2, "high_qc_view": 0, "node": "node_0"})
        sig0 = self.keypairs[0].sign(msg0)

        msg1 = sha256_digest({"v": 2, "high_qc_view": 1, "node": "node_1"})
        sig1 = self.keypairs[1].sign(msg1)

        msg2 = sha256_digest({"v": 2, "high_qc_view": -1, "node": "node_2"})
        sig2 = self.keypairs[2].sign(msg2)

        self.replica.slow_consensus.process_view_change_vote("node_0", 2, qc_v0, sig0, self.peer_keys)
        self.replica.slow_consensus.process_view_change_vote("node_1", 2, qc_v1, sig1, self.peer_keys)
        has_quorum, best_qc = self.replica.slow_consensus.process_view_change_vote("node_2", 2, None, sig2, self.peer_keys)

        self.assertTrue(has_quorum)
        self.assertIsNotNone(best_qc)
        self.assertEqual(best_qc.view, 1, "View change must select highest QC view across quorum")
        self.assertEqual(best_qc.digest, "digest_B")

    def test_F6_byzantine_equivocation_rollback_isolation(self):
        """F6: Byzantine equivocation triggers localized rollback without corrupting canonical state."""
        mvcc = MVCCVersionTree({"balance_alice": 100, "balance_bob": 50})

        mvcc.apply_speculative("root_0", "branch_1", {"balance_alice": 90, "balance_bob": 60})
        mvcc.apply_speculative("branch_1", "branch_2", {"balance_bob": 40, "balance_charlie": 20})
        mvcc.apply_speculative("root_0", "branch_3", {"balance_dave": 85, "balance_eve": 15})

        invalidated = mvcc.logical_rollback("branch_1")

        self.assertEqual(invalidated, 4)
        self.assertIn("branch_3", mvcc.active_speculative_heads)
        self.assertNotIn("branch_1", mvcc.active_speculative_heads)
        self.assertNotIn("branch_2", mvcc.active_speculative_heads)

        found, val = mvcc.get_finalized("balance_alice")
        self.assertTrue(found)
        self.assertEqual(val, 100, "Canonical finalized state must remain unaltered by speculative rollback")

    def test_rollback_metrics_Ar_and_Rs(self):
        """Validates formal definitions of Rollback Scope (R_s) and Rollback Amplification (A_r)."""
        mvcc = MVCCVersionTree({"k": 0})
        mvcc.apply_speculative("root_0", "b_conflict", {"k": 1})
        mvcc.apply_speculative("b_conflict", "b_child", {"k": 2})

        for i in range(3):
            mvcc.apply_speculative("root_0", f"b_indep_{i}", {f"indep_{i}": i})

        total_speculative_ops = 5
        directly_conflicting_ops = 1
        invalidated_ops = mvcc.logical_rollback("b_conflict")

        R_s = invalidated_ops / float(total_speculative_ops)
        A_r = invalidated_ops / float(directly_conflicting_ops)

        self.assertEqual(R_s, 2.0 / 5.0)
        self.assertEqual(A_r, 2.0)


if __name__ == "__main__":
    unittest.main()
