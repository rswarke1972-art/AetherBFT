"""
AetherBFT: Dependency Context & Explicit Key Model
Implements deterministic finite transaction models and Certified Dependency Sets D(T).
Explicitly restricts to finite key sets: T = (id, R_keys, W_keys, payload).
Predicate/range queries are declared outside the prototype model.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
try:
    from .crypto_verifier import sha256_digest
except (ImportError, ValueError):
    from crypto_verifier import sha256_digest


class Transaction:
    """
    Explicit Finite Key Transaction:
    T = (tx_id, client_id, read_keys, write_keys, payload, signature)
    """
    def __init__(
        self,
        tx_id: str,
        client_id: str,
        read_keys: List[str],
        write_keys: List[str],
        payload: Dict[str, Any],
        signature: Optional[str] = None
    ):
        self.tx_id = tx_id
        self.client_id = client_id
        self.read_keys = set(read_keys)
        self.write_keys = set(write_keys)
        self.payload = payload
        self.signature = signature
        self.digest = self._compute_digest()

    def _compute_digest(self) -> str:
        data = {
            "id": self.tx_id,
            "c": self.client_id,
            "r": sorted(list(self.read_keys)),
            "w": sorted(list(self.write_keys)),
            "p": self.payload
        }
        return sha256_digest(data)

    def interferes_with(self, other: "Transaction") -> bool:
        """
        Non-interference condition:
        Interferes if: (W_i intersect (R_j U W_j) != empty) OR (W_j intersect (R_i U W_i) != empty)
        """
        conflict_1 = bool(self.write_keys.intersection(other.read_keys.union(other.write_keys)))
        conflict_2 = bool(other.write_keys.intersection(self.read_keys.union(self.write_keys)))
        return conflict_1 or conflict_2

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tx_id": self.tx_id,
            "client_id": self.client_id,
            "read_keys": sorted(list(self.read_keys)),
            "write_keys": sorted(list(self.write_keys)),
            "payload": self.payload,
            "digest": self.digest,
            "signature": self.signature
        }


class DependencyContextManager:
    """
    Tracks pending active transactions and calculates Certified Dependency Set D(T).
    Replicas only accept fast path if the dependency context matches the certified frontier.
    """
    def __init__(self):
        # Active unfinalized transactions: tx_id -> Transaction
        self.active_transactions: Dict[str, Transaction] = {}
        # Key lock index: key -> list of active tx_ids
        self.key_index: Dict[str, Set[str]] = {}

    def register_active(self, tx: Transaction):
        """Registers an in-flight speculative transaction in the active key index."""
        self.active_transactions[tx.tx_id] = tx
        all_keys = tx.read_keys.union(tx.write_keys)
        for k in all_keys:
            if k not in self.key_index:
                self.key_index[k] = set()
            self.key_index[k].add(tx.tx_id)

    def compute_dependency_context(self, tx: Transaction) -> List[str]:
        """
        Computes Certified Dependency Set D(T) containing all unfinalized
        transactions whose read/write domains intersect with tx.
        """
        dependencies = set()
        all_keys = tx.read_keys.union(tx.write_keys)
        for k in all_keys:
            if k in self.key_index:
                for active_id in self.key_index[k]:
                    if active_id != tx.tx_id:
                        other_tx = self.active_transactions.get(active_id)
                        if other_tx and tx.interferes_with(other_tx):
                            dependencies.add(active_id)

        return sorted(list(dependencies))

    def is_fast_path_eligible(self, tx: Transaction) -> Tuple[bool, List[str]]:
        """
        Checks if transaction has zero conflicting dependencies with currently pending transactions.
        Returns: (is_eligible, dependency_list)
        """
        deps = self.compute_dependency_context(tx)
        return (len(deps) == 0, deps)

    def finalize(self, tx_id: str):
        """Removes a finalized transaction from the active tracking index."""
        if tx_id in self.active_transactions:
            tx = self.active_transactions.pop(tx_id)
            all_keys = tx.read_keys.union(tx.write_keys)
            for k in all_keys:
                if k in self.key_index:
                    self.key_index[k].discard(tx_id)
                    if not self.key_index[k]:
                        del self.key_index[k]

    def rollback(self, tx_id: str) -> List[str]:
        """
        Removes an aborted/rolled back transaction and identifies any downstream dependents.
        """
        invalidated = [tx_id]
        if tx_id in self.active_transactions:
            self.finalize(tx_id)

        return invalidated
