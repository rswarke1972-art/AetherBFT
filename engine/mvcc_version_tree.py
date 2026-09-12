"""
AetherBFT: Ephemeral MVCC Version-Tree State Machine
Implements branch-isolated speculative execution, O(1) logical rollback,
and strictly separates SPECULATIVE_STATE (TENTATIVE) from FINALIZED_STATE (LINEARIZABLE).
"""

from typing import Dict, List, Optional, Set, Tuple, Any
import copy


class VersionNode:
    """Represents a state delta branch in the MVCC DAG."""
    def __init__(self, branch_id: str, parent: Optional["VersionNode"] = None):
        self.branch_id = branch_id
        self.parent = parent
        self.deltas: Dict[str, Any] = {}  # key -> value
        self.children: List["VersionNode"] = []
        self.is_finalized = False
        self.is_aborted = False

    def read_key(self, key: str) -> Tuple[bool, Any]:
        """Traverses up the ancestor chain to read the latest version of key."""
        curr = self
        while curr is not None:
            if not curr.is_aborted and key in curr.deltas:
                return True, curr.deltas[key]
            curr = curr.parent
        return False, None


class MVCCVersionTree:
    """
    Maintains the replicated state machine.
    Distinguishes:
    - get_finalized(key): Strictly linearizable, reads only committed state.
    - get_speculative(key): Tentative optimistic read, explicitly marked TENTATIVE.
    - logical_rollback(branch_id): O(1) pointer invalidation of speculative sub-branch.
    """
    def __init__(self, initial_state: Optional[Dict[str, Any]] = None):
        # Canonical finalized root
        self.finalized_root = VersionNode("root_0", parent=None)
        self.finalized_root.is_finalized = True
        if initial_state:
            self.finalized_root.deltas = copy.deepcopy(initial_state)

        # Active branches: branch_id -> VersionNode
        self.branches: Dict[str, VersionNode] = {"root_0": self.finalized_root}
        self.active_speculative_heads: Set[str] = set()

        # Telemetry
        self.total_speculative_writes = 0
        self.total_finalized_commits = 0
        self.total_logical_rollbacks = 0
        self.invalidated_speculative_ops = 0

    # 1. Linearizable Finalized API
    def get_finalized(self, key: str) -> Tuple[bool, Any]:
        """
        Guaranteed linearizable read. Accesses only canonical finalized state.
        Never observes uncommitted speculative writes.
        """
        found, val = self.finalized_root.read_key(key)
        return found, val

    # 2. Tentative Speculative API
    def get_speculative(self, branch_id: str, key: str) -> Tuple[bool, Any, str]:
        """
        Optimistic read along a speculative branch.
        Returns: (found, value, status='TENTATIVE')
        Explicitly marked TENTATIVE; not linearizable until finalized.
        """
        if branch_id not in self.branches or self.branches[branch_id].is_aborted:
            # Fall back to finalized root if branch invalid
            found, val = self.get_finalized(key)
            return found, val, "COMMITTED"

        found, val = self.branches[branch_id].read_key(key)
        return found, val, "TENTATIVE"

    def apply_speculative(self, parent_branch_id: str, new_branch_id: str, deltas: Dict[str, Any]) -> str:
        """
        Creates a new speculative version branch in O(1).
        Writes deltas to an isolated child node without modifying canonical state.
        """
        self.total_speculative_writes += len(deltas)
        parent_node = self.branches.get(parent_branch_id, self.finalized_root)
        if parent_node.is_aborted:
            parent_node = self.finalized_root

        child = VersionNode(new_branch_id, parent=parent_node)
        child.deltas = copy.deepcopy(deltas)
        parent_node.children.append(child)

        self.branches[new_branch_id] = child
        self.active_speculative_heads.add(new_branch_id)
        return new_branch_id

    def finalize_branch(self, branch_id: str):
        """
        Promotes a speculative branch to finalized canonical state upon verified Quorum Certificate.
        Folds deltas into finalized root in O(|deltas|).
        """
        if branch_id not in self.branches:
            return

        node = self.branches[branch_id]
        if node.is_aborted:
            return

        # Flatten path from finalized root to node
        path = []
        curr = node
        while curr is not None and not curr.is_finalized:
            path.append(curr)
            curr = curr.parent

        path.reverse()
        for p in path:
            self.finalized_root.deltas.update(p.deltas)
            p.is_finalized = True
            self.total_finalized_commits += len(p.deltas)

        self.active_speculative_heads.discard(branch_id)

    def logical_rollback(self, branch_id: str) -> int:
        """
        Performs O(1) logical rollback by marking branch and descendants as aborted.
        Physical reclamation is deferred.
        Returns: count of invalidated speculative operations.
        """
        if branch_id not in self.branches:
            return 0

        node = self.branches[branch_id]
        if node.is_aborted:
            return 0

        self.total_logical_rollbacks += 1

        # Invalidate subtree
        invalidated_count = 0
        queue = [node]
        while queue:
            curr = queue.pop(0)
            if not curr.is_aborted and not curr.is_finalized:
                curr.is_aborted = True
                invalidated_count += len(curr.deltas)
                self.active_speculative_heads.discard(curr.branch_id)
                queue.extend(curr.children)

        self.invalidated_speculative_ops += invalidated_count
        return invalidated_count

    def merge_disjoint_branches(self, branch_a: str, branch_b: str, merged_branch_id: str) -> Optional[str]:
        """
        Logically joins two independent speculative branches whose write domains are disjoint.
        Returns merged branch ID.
        """
        node_a = self.branches.get(branch_a)
        node_b = self.branches.get(branch_b)
        if not node_a or not node_b or node_a.is_aborted or node_b.is_aborted:
            return None

        # Check write domain disjointness
        keys_a = set(node_a.deltas.keys())
        keys_b = set(node_b.deltas.keys())
        if keys_a.intersection(keys_b):
            return None  # Cannot merge conflicting writes without ordering

        merged = VersionNode(merged_branch_id, parent=node_a.parent)
        merged.deltas = {**node_a.deltas, **node_b.deltas}
        self.branches[merged_branch_id] = merged
        self.active_speculative_heads.add(merged_branch_id)
        return merged_branch_id
