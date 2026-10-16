"""jarvis_learning.datasets.merkle_manifest — dataset Merkle tree and inclusion proofs.

Provides:
- Dataset-wide tamper verification through a binary Merkle root.
- Individual sample membership verification through logarithmic O(log n) Merkle proofs.
"""

from __future__ import annotations

import hashlib
from typing import Sequence


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _combine_hashes(left: str, right: str) -> str:
    combined = (left + ":" + right).encode("utf-8")
    return hashlib.sha256(combined).hexdigest()


class MerkleTree:
    """Constructs a binary Merkle tree over sorted sample digests."""

    def __init__(self, leaf_digests: Sequence[str]) -> None:
        # Sort leaf digests deterministically
        self._leaves = sorted(leaf_digests)
        self._levels: list[list[str]] = []
        self._build_tree()

    @property
    def root(self) -> str:
        """Return the root hash of the Merkle tree."""
        if not self._levels or not self._levels[0]:
            return hashlib.sha256(b"empty_merkle").hexdigest()
        return self._levels[-1][0]

    @property
    def leaves(self) -> list[str]:
        return list(self._leaves)

    def _build_tree(self) -> None:
        if not self._leaves:
            self._levels = [[hashlib.sha256(b"empty_merkle").hexdigest()]]
            return

        current_level = list(self._leaves)
        self._levels.append(current_level)

        while len(current_level) > 1:
            next_level: list[str] = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                if i + 1 < len(current_level):
                    right = current_level[i + 1]
                else:
                    # Odd element duplicated at boundary
                    right = current_level[i]
                next_level.append(_combine_hashes(left, right))
            current_level = next_level
            self._levels.append(current_level)

    def generate_proof(self, leaf_digest: str) -> list[tuple[str, str]]:
        """Generate Merkle inclusion proof for a leaf digest.

        Returns list of (direction, sibling_hash) tuples, where direction is 'L' or 'R'.
        """
        if leaf_digest not in self._leaves:
            raise ValueError(f"Leaf digest {leaf_digest} not found in Merkle tree")

        idx = self._leaves.index(leaf_digest)
        proof: list[tuple[str, str]] = []

        for level in self._levels[:-1]:
            is_right = idx % 2 == 1
            sibling_idx = idx - 1 if is_right else idx + 1
            if sibling_idx < len(level):
                sibling_hash = level[sibling_idx]
            else:
                sibling_hash = level[idx]

            direction = "L" if is_right else "R"
            proof.append((direction, sibling_hash))
            idx //= 2

        return proof

    def get_proof(self, target: int | str) -> list[tuple[str, str]]:
        """Get proof by leaf index or leaf digest string."""
        if isinstance(target, int):
            if target < 0 or target >= len(self._leaves):
                raise IndexError(f"Leaf index {target} out of range")
            leaf = self._leaves[target]
        else:
            leaf = target
        return self.generate_proof(leaf)

    @staticmethod
    def verify_proof(leaf_digest: str, proof: list[tuple[str, str]], root: str) -> bool:
        """Verify an O(log n) Merkle inclusion proof against a known root."""
        current = leaf_digest
        for direction, sibling in proof:
            if direction == "L":
                current = _combine_hashes(sibling, current)
            else:
                current = _combine_hashes(current, sibling)
        return current == root
