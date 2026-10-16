"""Stable loss functions with exact analytical gradients."""

from __future__ import annotations

import numpy as np


class CrossEntropyLoss:
    """Stable CrossEntropyLoss with log-sum-exp trick and ignore_index support."""

    def __init__(self, ignore_index: int = -100) -> None:
        self.ignore_index = ignore_index
        self._cache: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int] | None = None

    def forward(self, logits: np.ndarray, targets: np.ndarray) -> float:
        """Computes cross entropy loss.

        Args:
            logits: Unnormalized log probabilities (..., num_classes)
            targets: Class labels (...) with integer indices, or -100 for ignore.

        Returns:
            Scalar mean loss.
        """
        orig_shape = logits.shape
        num_classes = orig_shape[-1]
        flat_logits = logits.reshape(-1, num_classes)
        flat_targets = targets.reshape(-1)

        # Mask ignored tokens
        valid_mask = flat_targets != self.ignore_index
        n_valid = int(np.sum(valid_mask))
        if n_valid == 0:
            return 0.0

        # Log-sum-exp trick for numerical stability
        max_logits = np.max(flat_logits, axis=-1, keepdims=True)
        exp_logits = np.exp(flat_logits - max_logits)
        sum_exp = np.sum(exp_logits, axis=-1, keepdims=True)
        log_probs = (flat_logits - max_logits) - np.log(sum_exp)
        probs = exp_logits / sum_exp

        # Gather target log-probabilities for valid items
        valid_targets = flat_targets[valid_mask]
        valid_log_probs = log_probs[valid_mask]
        target_log_probs = valid_log_probs[np.arange(n_valid), valid_targets]

        loss = -float(np.mean(target_log_probs))
        self._cache = (flat_logits, flat_targets, probs, valid_mask, n_valid)
        return loss

    def backward(self) -> np.ndarray:
        """Analytical gradient dL/d(logits)."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        flat_logits, flat_targets, probs, valid_mask, n_valid = self._cache
        if n_valid == 0:
            return np.zeros_like(flat_logits)

        grad = probs.copy()
        # dL/dz_i = (P_i - y_i) / N_valid
        for i in range(len(flat_targets)):
            if valid_mask[i]:
                t = flat_targets[i]
                grad[i, t] -= 1.0
            else:
                grad[i, :] = 0.0

        grad /= float(n_valid)
        return grad
