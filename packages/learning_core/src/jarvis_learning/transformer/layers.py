"""Activation functions and Position-wise Feed-Forward Network."""

from __future__ import annotations

import numpy as np


def gelu(x: np.ndarray) -> np.ndarray:
    """GELU activation function with standard tanh approximation."""
    sqrt_2_over_pi = np.sqrt(2.0 / np.pi)
    inner = sqrt_2_over_pi * (x + 0.044715 * (x**3))
    return 0.5 * x * (1.0 + np.tanh(inner))


def gelu_prime(x: np.ndarray) -> np.ndarray:
    """Exact derivative of GELU tanh approximation."""
    sqrt_2_over_pi = np.sqrt(2.0 / np.pi)
    inner = sqrt_2_over_pi * (x + 0.044715 * (x**3))
    tanh_inner = np.tanh(inner)
    d_inner = sqrt_2_over_pi * (1.0 + 3.0 * 0.044715 * (x**2))
    sech2 = 1.0 - (tanh_inner**2)
    return 0.5 * (1.0 + tanh_inner) + 0.5 * x * sech2 * d_inner


def relu(x: np.ndarray) -> np.ndarray:
    """ReLU activation."""
    return np.maximum(0.0, x)


def relu_prime(x: np.ndarray) -> np.ndarray:
    """Derivative of ReLU."""
    return (x > 0.0).astype(np.float64)


class PositionwiseFeedForward:
    """Two-layer feedforward network with GELU/ReLU activation."""

    def __init__(
        self,
        d_model: int,
        d_ff: int,
        activation: str = "gelu",
        use_bias: bool = True,
        rng: np.random.Generator | None = None,
    ) -> None:
        self.d_model = d_model
        self.d_ff = d_ff
        self.activation_name = activation
        self.use_bias = use_bias
        if rng is None:
            rng = np.random.default_rng()

        std1 = np.sqrt(2.0 / d_model)
        self.w1 = rng.normal(0.0, std1, size=(d_model, d_ff)).astype(np.float64)
        self.b1 = np.zeros((d_ff,), dtype=np.float64) if use_bias else None

        std2 = np.sqrt(2.0 / d_ff)
        self.w2 = rng.normal(0.0, std2, size=(d_ff, d_model)).astype(np.float64)
        self.b2 = np.zeros((d_model,), dtype=np.float64) if use_bias else None

        self._cache: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Forward pass: x -> Linear(w1) -> Act -> Linear(w2) -> out."""
        h1 = x @ self.w1
        if self.b1 is not None:
            h1 = h1 + self.b1

        if self.activation_name == "gelu":
            a1 = gelu(h1)
        else:
            a1 = relu(h1)

        out = a1 @ self.w2
        if self.b2 is not None:
            out = out + self.b2

        self._cache = (x, h1, a1)
        return out

    def backward(self, grad_output: np.ndarray) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """Analytical backward pass for FFN."""
        if self._cache is None:
            raise RuntimeError("Cannot call backward before forward")

        x, h1, a1 = self._cache

        grad_w2 = a1.reshape(-1, self.d_ff).T @ grad_output.reshape(-1, self.d_model)
        grad_params: dict[str, np.ndarray] = {"w2": grad_w2}

        if self.b2 is not None:
            grad_params["b2"] = np.sum(grad_output, axis=tuple(range(grad_output.ndim - 1)))

        grad_a1 = grad_output @ self.w2.T

        if self.activation_name == "gelu":
            act_p = gelu_prime(h1)
        else:
            act_p = relu_prime(h1)

        grad_h1 = grad_a1 * act_p

        grad_w1 = x.reshape(-1, self.d_model).T @ grad_h1.reshape(-1, self.d_ff)
        grad_params["w1"] = grad_w1

        if self.b1 is not None:
            grad_params["b1"] = np.sum(grad_h1, axis=tuple(range(grad_h1.ndim - 1)))

        grad_x = grad_h1 @ self.w1.T
        return grad_x, grad_params
