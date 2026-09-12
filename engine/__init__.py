"""
AetherBFT Engine: Dependency-Aware Speculative BFT Consensus Protocol
"""

try:
    from .crypto_verifier import KeyPair, QuorumCertificate, ProofOfEquivocation, sha256_digest
except (ImportError, ValueError):
    from crypto_verifier import KeyPair, QuorumCertificate, ProofOfEquivocation, sha256_digest
try:
    from .dependency_context import Transaction, DependencyContextManager
except (ImportError, ValueError):
    from dependency_context import Transaction, DependencyContextManager
try:
    from .mvcc_version_tree import MVCCVersionTree, VersionNode
except (ImportError, ValueError):
    from mvcc_version_tree import MVCCVersionTree, VersionNode
try:
    from .fast_path_router import FastPathRouter
except (ImportError, ValueError):
    from fast_path_router import FastPathRouter
try:
    from .slow_path_consensus import SlowPathConsensus
except (ImportError, ValueError):
    from slow_path_consensus import SlowPathConsensus
try:
    from .node_replica import AetherReplica
except (ImportError, ValueError):
    from node_replica import AetherReplica

__all__ = [
    "KeyPair",
    "QuorumCertificate",
    "ProofOfEquivocation",
    "sha256_digest",
    "Transaction",
    "DependencyContextManager",
    "MVCCVersionTree",
    "VersionNode",
    "FastPathRouter",
    "SlowPathConsensus",
    "AetherReplica"
]
