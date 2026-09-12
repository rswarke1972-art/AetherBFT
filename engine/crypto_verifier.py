"""
AetherBFT: Cryptographic Verifier & Quorum Certificate Engine
Implements Ed25519 asymmetric signing, Quorum Certificates (QC),
and Proof of Equivocation (PoE) detection with peer quarantine.
"""

import hashlib
import json
from typing import Dict, List, Optional, Tuple, Any
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.exceptions import InvalidSignature


def sha256_digest(data: Any) -> str:
    """Computes deterministic SHA-256 hex digest of string or dict."""
    if isinstance(data, dict) or isinstance(data, list):
        serialized = json.dumps(data, sort_keys=True)
    elif isinstance(data, bytes):
        serialized = data.decode("utf-8", errors="replace")
    else:
        serialized = str(data)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class KeyPair:
    """Manages an Ed25519 asymmetric signing key pair."""
    def __init__(self, private_key: Optional[ed25519.Ed25519PrivateKey] = None):
        self._private_key = private_key or ed25519.Ed25519PrivateKey.generate()
        self._public_key = self._private_key.public_key()
        self.public_bytes = self._public_key.public_bytes_raw()
        self.public_hex = self.public_bytes.hex()

    def sign(self, message: str) -> str:
        """Signs a UTF-8 message, returning hex-encoded signature."""
        sig_bytes = self._private_key.sign(message.encode("utf-8"))
        return sig_bytes.hex()

    @staticmethod
    def verify(public_hex: str, message: str, signature_hex: str) -> bool:
        """Verifies an Ed25519 signature against a public key."""
        try:
            pub_bytes = bytes.fromhex(public_hex)
            sig_bytes = bytes.fromhex(signature_hex)
            pub_key = ed25519.Ed25519PublicKey.from_public_bytes(pub_bytes)
            pub_key.verify(sig_bytes, message.encode("utf-8"))
            return True
        except (InvalidSignature, ValueError, Exception):
            return False


class QuorumCertificate:
    """
    Formal BFT Quorum Certificate:
    QC = (view, sequence, digest H(T), dependency_context D(T), signatures Sigma_Q)
    """
    def __init__(
        self,
        view: int,
        sequence: int,
        digest: str,
        dependency_context: List[str],
        signatures: Dict[str, str],  # node_id -> signature_hex
        is_fast_path: bool = False
    ):
        self.view = view
        self.sequence = sequence
        self.digest = digest
        self.dependency_context = sorted(dependency_context)
        self.signatures = signatures
        self.is_fast_path = is_fast_path

    @property
    def message_payload(self) -> str:
        """Canonical message representation signed by replicas."""
        data = {
            "v": self.view,
            "s": self.sequence,
            "h": self.digest,
            "d": self.dependency_context
        }
        return json.dumps(data, sort_keys=True)

    def verify_quorum(self, quorum_size: int, peer_public_keys: Dict[str, str]) -> bool:
        """Verifies that at least quorum_size valid signatures are present."""
        if len(self.signatures) < quorum_size:
            return False

        valid_count = 0
        msg = self.message_payload
        for node_id, sig_hex in self.signatures.items():
            if node_id not in peer_public_keys:
                continue
            pub_hex = peer_public_keys[node_id]
            if KeyPair.verify(pub_hex, msg, sig_hex):
                valid_count += 1

        return valid_count >= quorum_size

    def to_dict(self) -> Dict[str, Any]:
        return {
            "view": self.view,
            "sequence": self.sequence,
            "digest": self.digest,
            "dependency_context": self.dependency_context,
            "signatures": self.signatures,
            "is_fast_path": self.is_fast_path
        }


class ProofOfEquivocation:
    """
    Cryptographic proof that a node signed two distinct proposals for the same (view, sequence).
    """
    def __init__(
        self,
        offending_node: str,
        view: int,
        sequence: int,
        digest_1: str,
        sig_1: str,
        digest_2: str,
        sig_2: str
    ):
        self.offending_node = offending_node
        self.view = view
        self.sequence = sequence
        self.digest_1 = digest_1
        self.sig_1 = sig_1
        self.digest_2 = digest_2
        self.sig_2 = sig_2

    def verify(self, peer_public_keys: Dict[str, str]) -> bool:
        """Confirms that the offending node signed two distinct digests for the same slot."""
        if self.digest_1 == self.digest_2:
            return False  # Not equivocation if identical
        if self.offending_node not in peer_public_keys:
            return False

        pub_hex = peer_public_keys[self.offending_node]
        msg1 = json.dumps({"v": self.view, "s": self.sequence, "h": self.digest_1}, sort_keys=True)
        msg2 = json.dumps({"v": self.view, "s": self.sequence, "h": self.digest_2}, sort_keys=True)

        valid_1 = KeyPair.verify(pub_hex, msg1, self.sig_1)
        valid_2 = KeyPair.verify(pub_hex, msg2, self.sig_2)
        return valid_1 and valid_2
