"""Task-specific heads and pooling layers with exact analytical backward passes."""

from __future__ import annotations

import numpy as np


class LastValidTokenPooling:
    """Extracts representation at the last non-padded token position.

    Guarantees that trailing <pad> tokens do not dilute or corrupt
    task-head inputs.
    """

    def __init__(self) -> None:
        self._cache: tuple[list[int], tuple[int, ...]] | None = None

    def forward(
        self, hidden_states: np.ndarray, padding_mask: np.ndarray | None = None
    ) -> np.ndarray:
        """Pulls the last valid token representation per batch item.

        Args:
            hidden_states: (B, T, d_model)
            padding_mask: (B, T) boolean mask where True=valid, False=pad.

        Returns:
            pooled: (B, d_model)
        """
        b, t, d = hidden_states.shape
        pooled = np.zeros((b, d), dtype=np.float64)
        last_indices: list[int] = []

        for i in range(b):
            if padding_mask is not None:
                valid = np.where(padding_mask[i])[0]
                idx = int(valid[-1]) if len(valid) > 0 else 0
            else:
                idx = t - 1
            last_indices.append(idx)
            pooled[i] = hidden_states[i, idx, :]

        self._cache = (last_indices, hidden_states.shape)
        return pooled

    def backward(self, grad_pooled: np.ndarray) -> np.ndarray:
        """Scatters gradients from pooled representations back to last valid token positions."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        last_indices, (b, t, d) = self._cache
        grad_hidden = np.zeros((b, t, d), dtype=np.float64)

        for i in range(b):
            idx = last_indices[i]
            grad_hidden[i, idx, :] = grad_pooled[i]

        return grad_hidden


class ToolClassificationHead:
    """Multi-class classification head for selecting among registered tool actions."""

    def __init__(
        self,
        d_model: int,
        num_classes: int,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.d_model = d_model
        self.num_classes = num_classes
        if rng is None:
            rng = np.random.default_rng()

        std = 1.0 / np.sqrt(d_model)
        self.w = rng.normal(0.0, std, size=(d_model, num_classes)).astype(np.float64)
        self.b = np.zeros((num_classes,), dtype=np.float64)

        self._cache: np.ndarray | None = None

    def forward(self, pooled_h: np.ndarray) -> np.ndarray:
        """Computes unnormalized class logits of shape (B, num_classes)."""
        self._cache = pooled_h
        return pooled_h @ self.w + self.b

    def backward(self, grad_logits: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Analytical backward pass."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        pooled_h = self._cache
        grad_w = pooled_h.T @ grad_logits
        grad_b = np.sum(grad_logits, axis=0)
        grad_h = grad_logits @ self.w.T

        return grad_h, {"w": grad_w, "b": grad_b}


class OutcomePredictionHead:
    """Binary/scalar prediction head for estimating task success probabilities."""

    def __init__(
        self,
        d_model: int,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.d_model = d_model
        if rng is None:
            rng = np.random.default_rng()

        std = 1.0 / np.sqrt(d_model)
        self.w = rng.normal(0.0, std, size=(d_model, 1)).astype(np.float64)
        self.b = np.zeros((1,), dtype=np.float64)

        self._cache: np.ndarray | None = None

    def forward(self, pooled_h: np.ndarray) -> np.ndarray:
        """Computes scalar logit of shape (B, 1)."""
        self._cache = pooled_h
        return pooled_h @ self.w + self.b

    def backward(self, grad_logits: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Analytical backward pass."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        pooled_h = self._cache
        grad_w = pooled_h.T @ grad_logits
        grad_b = np.sum(grad_logits, axis=0)
        grad_h = grad_logits @ self.w.T

        return grad_h, {"w": grad_w, "b": grad_b}


class CausalLMHead:
    """Language modeling head mapping hidden states (B, T, d_model) to vocab logits (B, T, vocab_size)."""

    def __init__(
        self,
        d_model: int,
        vocab_size: int,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.d_model = d_model
        self.vocab_size = vocab_size
        if rng is None:
            rng = np.random.default_rng()

        std = 1.0 / np.sqrt(d_model)
        self.w = rng.normal(0.0, std, size=(d_model, vocab_size)).astype(np.float64)
        self.b = np.zeros((vocab_size,), dtype=np.float64)

        self._cache: np.ndarray | None = None

    def forward(self, hidden_states: np.ndarray) -> np.ndarray:
        self._cache = hidden_states
        return hidden_states @ self.w + self.b

    def backward(self, grad_logits: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        hidden_states = self._cache
        b, t, d = hidden_states.shape
        flat_h = hidden_states.reshape(-1, d)
        flat_grad = grad_logits.reshape(-1, self.vocab_size)

        grad_w = flat_h.T @ flat_grad
        grad_b = np.sum(flat_grad, axis=0)
        flat_grad_h = flat_grad @ self.w.T
        grad_h = flat_grad_h.reshape(b, t, d)

        return grad_h, {"w": grad_w, "b": grad_b}
