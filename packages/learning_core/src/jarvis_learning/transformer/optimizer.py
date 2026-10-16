"""AdamW optimizer implemented from scratch in pure NumPy."""

from __future__ import annotations

from typing import Any
import numpy as np


class AdamW:
    """AdamW optimizer with decoupled weight decay and parameter group segregation.

    Decoupled weight decay is applied only to 2D weight matrices (e.g. projections, linear layers),
    and specifically NOT applied to 1D vectors (biases, layer norm gamma/beta).
    """

    def __init__(
        self,
        params: dict[str, Any],
        lr: float = 1e-3,
        betas: tuple[float, float] = (0.9, 0.999),
        eps: float = 1e-8,
        weight_decay: float = 0.01,
    ) -> None:
        self.params = params
        self.lr = lr
        self.beta1, self.beta2 = betas
        self.eps = eps
        self.weight_decay = weight_decay

        self.step_count: int = 0
        self.m: dict[str, np.ndarray] = {}
        self.v: dict[str, np.ndarray] = {}

    def _flatten_params(self, structure: Any, prefix: str = "") -> dict[str, np.ndarray]:
        flat: dict[str, np.ndarray] = {}
        if isinstance(structure, np.ndarray):
            flat[prefix] = structure
        elif isinstance(structure, dict):
            for k, v in structure.items():
                p = f"{prefix}.{k}" if prefix else str(k)
                flat.update(self._flatten_params(v, p))
        elif isinstance(structure, (list, tuple)):
            for i, v in enumerate(structure):
                p = f"{prefix}.{i}" if prefix else str(i)
                flat.update(self._flatten_params(v, p))
        return flat

    def step(self, grads: dict[str, Any], current_lr: float | None = None) -> None:
        """Executes a single optimization step given gradient structure."""
        self.step_count += 1
        lr = self.lr if current_lr is None else current_lr

        flat_params = self._flatten_params(self.params)
        flat_grads = self._flatten_params(grads)

        # Precompute bias corrections
        b1_corr = 1.0 - (self.beta1**self.step_count)
        b2_corr = 1.0 - (self.beta2**self.step_count)

        for name, p in flat_params.items():
            if name not in flat_grads:
                continue

            g = flat_grads[name]

            # Initialize moment buffers if first step
            if name not in self.m:
                self.m[name] = np.zeros_like(p)
                self.v[name] = np.zeros_like(p)

            # Update biased 1st and 2nd moment estimates
            self.m[name] = self.beta1 * self.m[name] + (1.0 - self.beta1) * g
            self.v[name] = self.beta2 * self.v[name] + (1.0 - self.beta2) * (g**2)

            # Compute bias-corrected moments
            m_hat = self.m[name] / b1_corr
            v_hat = self.v[name] / b2_corr

            # Decoupled weight decay applied ONLY to 2D weight matrices (not biases or LayerNorm)
            is_2d_weight = p.ndim >= 2 and not any(
                skip in name.lower() for skip in ("bias", "beta", "gamma", "ln")
            )
            if is_2d_weight and self.weight_decay > 0.0:
                p -= lr * self.weight_decay * p

            # Adam step update
            step_update = lr * m_hat / (np.sqrt(v_hat) + self.eps)
            p -= step_update

    def zero_grad(self) -> None:
        """No-op for AdamW since gradients are passed explicitly to step()."""
        pass


def get_lr_schedule(
    step: int,
    base_lr: float,
    warmup_steps: int,
    max_steps: int,
    min_lr: float = 1e-5,
) -> float:
    """Computes learning rate with linear warmup and cosine decay."""
    if step < warmup_steps:
        return float(base_lr * (step + 1) / max(1, warmup_steps))
    elif step >= max_steps:
        return float(min_lr)
    else:
        progress = float(step - warmup_steps) / float(max(1, max_steps - warmup_steps))
        cosine_decay = 0.5 * (1.0 + np.cos(np.pi * progress))
        return float(min_lr + (base_lr - min_lr) * cosine_decay)
