"""KV Cache for incremental autoregressive generation in O(1) step complexity."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class KVCacheEntry:
    """Key and Value tensors for a single attention layer."""

    key: np.ndarray | None = None  # Shape: (B, H, T_past, d_k)
    value: np.ndarray | None = None  # Shape: (B, H, T_past, d_v)


class KVCache:
    """Manages multi-layer Key-Value caching for autoregressive inference."""

    def __init__(self, n_layers: int) -> None:
        self.n_layers = n_layers
        self.entries: list[KVCacheEntry] = [KVCacheEntry() for _ in range(n_layers)]

    def get(self, layer_idx: int) -> tuple[np.ndarray | None, np.ndarray | None]:
        entry = self.entries[layer_idx]
        return entry.key, entry.value

    def update(
        self, layer_idx: int, key: np.ndarray, value: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Appends new key/value along the sequence dimension (axis 2)."""
        entry = self.entries[layer_idx]
        if entry.key is None or entry.value is None:
            entry.key = key
            entry.value = value
        else:
            entry.key = np.concatenate([entry.key, key], axis=2)
            entry.value = np.concatenate([entry.value, value], axis=2)
        return entry.key, entry.value

    def clear(self) -> None:
        for entry in self.entries:
            entry.key = None
            entry.value = None

    @property
    def current_seq_len(self) -> int:
        if self.entries and self.entries[0].key is not None:
            return self.entries[0].key.shape[2]
        return 0
