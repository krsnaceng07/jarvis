"""LayerNorm implementation with exact analytical backward pass."""

from __future__ import annotations

import numpy as np


class LayerNorm:
    """Layer Normalization over the last dimension (d_model)."""

    def __init__(self, d_model: int, eps: float = 1e-5) -> None:
        self.d_model = d_model
        self.eps = eps
        self.gamma = np.ones((d_model,), dtype=np.float64)
        self.beta = np.zeros((d_model,), dtype=np.float64)

        # Forward cache for backprop
        self._cache: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass for LayerNorm.

        Args:
            x: Input tensor of shape (..., d_model)

        Returns:
            Normalized tensor of same shape as x.
        """
        mean = np.mean(x, axis=-1, keepdims=True)
        var = np.var(x, axis=-1, keepdims=True)
        std_inv = 1.0 / np.sqrt(var + self.eps)
        x_hat = (x - mean) * std_inv
        y = self.gamma * x_hat + self.beta

        self._cache = (x, mean, std_inv, x_hat)
        return y

    def backward(self, grad_output: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Exact analytical gradient calculation for LayerNorm.

        Returns:
            (grad_x, {"gamma": grad_gamma, "beta": grad_beta})
        """
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        x, mean, std_inv, x_hat = self._cache
        reduce_axes = tuple(range(grad_output.ndim - 1))

        dgamma = np.sum(grad_output * x_hat, axis=reduce_axes)
        dbeta = np.sum(grad_output, axis=reduce_axes)

        dx_hat = grad_output * self.gamma

        # Standard closed form:
        # dx = std_inv * (dx_hat - mean(dx_hat) - x_hat * mean(dx_hat * x_hat))
        mean_dx_hat = np.mean(dx_hat, axis=-1, keepdims=True)
        mean_dx_hat_x_hat = np.mean(dx_hat * x_hat, axis=-1, keepdims=True)
        dx = std_inv * (dx_hat - mean_dx_hat - x_hat * mean_dx_hat_x_hat)

        return dx, {"gamma": dgamma, "beta": dbeta}
