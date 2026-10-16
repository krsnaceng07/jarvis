"""Token and Positional Embeddings in pure NumPy."""

from __future__ import annotations

import numpy as np


class TokenEmbedding:
    """Learnable token embedding lookup table."""

    def __init__(
        self, vocab_size: int, d_model: int, rng: np.random.Generator | None = None
    ) -> None:
        self.vocab_size = vocab_size
        self.d_model = d_model
        if rng is None:
            rng = np.random.default_rng()
        self.weight = rng.normal(0.0, 1.0 / np.sqrt(d_model), size=(vocab_size, d_model)).astype(
            np.float64
        )
        self._cached_input_ids: np.ndarray | None = None

    def forward(self, input_ids: np.ndarray) -> np.ndarray:
        """Looks up embedding vectors for input_ids of shape (B, T).

        Returns:
            np.ndarray of shape (B, T, d_model)
        """
        self._cached_input_ids = input_ids
        return self.weight[input_ids]

    def backward(self, grad_output: np.ndarray) -> dict[str, np.ndarray]:
        """Computes weight gradients by scattering grad_output back to embedding rows."""
        if self._cached_input_ids is None:
            raise RuntimeError("Cannot call backward before forward")
        grad_weight = np.zeros_like(self.weight)
        np.add.at(grad_weight, self._cached_input_ids, grad_output)
        return {"weight": grad_weight}


class SinusoidalPositionalEncoding:
    """Standard sinusoidal positional encoding table (non-learnable)."""

    def __init__(self, max_seq_len: int, d_model: int) -> None:
        self.max_seq_len = max_seq_len
        self.d_model = d_model

        pe = np.zeros((max_seq_len, d_model), dtype=np.float64)
        position = np.arange(0, max_seq_len, dtype=np.float64)[:, np.newaxis]
        div_term = np.exp(np.arange(0, d_model, 2, dtype=np.float64) * (-np.log(10000.0) / d_model))

        pe[:, 0::2] = np.sin(position * div_term)
        pe[:, 1::2] = np.cos(position * div_term)
        self.pe = pe[np.newaxis, :, :]  # Shape: (1, max_seq_len, d_model)

    def forward(self, seq_len: int) -> np.ndarray:
        """Returns positional encoding slice for sequence length (1, seq_len, d_model)."""
        return self.pe[:, :seq_len, :]


class LearnedPositionalEncoding:
    """Learnable positional embedding table."""

    def __init__(
        self, max_seq_len: int, d_model: int, rng: np.random.Generator | None = None
    ) -> None:
        self.max_seq_len = max_seq_len
        self.d_model = d_model
        if rng is None:
            rng = np.random.default_rng()
        self.weight = rng.normal(0.0, 1.0 / np.sqrt(d_model), size=(max_seq_len, d_model)).astype(
            np.float64
        )
        self._cached_seq_len: int = 0

    def forward(self, seq_len: int) -> np.ndarray:
        self._cached_seq_len = seq_len
        return self.weight[:seq_len, :][np.newaxis, :, :]

    def backward(self, grad_output: np.ndarray) -> dict[str, np.ndarray]:
        grad_weight = np.zeros_like(self.weight)
        # grad_output shape: (B, T, d_model) -> sum across batch
        grad_weight[: self._cached_seq_len] = np.sum(grad_output, axis=0)
        return {"weight": grad_weight}
