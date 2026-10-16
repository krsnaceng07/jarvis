"""Finite-difference numerical gradient checking utility."""

from __future__ import annotations

from typing import Callable
import numpy as np

from jarvis_learning.transformer.errors import GradientCheckFailedError


def check_gradients(
    func: Callable[[np.ndarray], float],
    x: np.ndarray,
    grad_analytical: np.ndarray,
    eps: float = 1e-5,
    tol: float = 1e-4,
    max_samples: int = 50,
    raise_on_failure: bool = True,
) -> tuple[bool, float]:
    """Validates analytical gradient against two-sided finite difference.

    Formula:
        g_num = (func(x + eps) - func(x - eps)) / (2 * eps)
        rel_error = |g_ana - g_num| / max(|g_ana|, |g_num|, 1e-7)

    Args:
        func: Scalar loss function of x
        x: Point at which gradient was evaluated
        grad_analytical: Analytical gradient array of same shape as x
        eps: Finite difference perturbation step
        tol: Maximum allowable relative error (default 1e-4)
        max_samples: Maximum number of coordinates to check (for efficiency)
        raise_on_failure: Whether to raise GradientCheckFailedError if check fails

    Returns:
        (passed, max_relative_error)
    """
    flat_x = x.flatten()
    flat_grad_ana = grad_analytical.flatten()
    total_elements = len(flat_x)

    if total_elements <= max_samples:
        indices = np.arange(total_elements)
    else:
        rng = np.random.default_rng(42)
        indices = rng.choice(total_elements, size=max_samples, replace=False)

    max_rel_err = 0.0

    for idx in indices:
        orig_val = flat_x[idx]

        # x + eps
        flat_x[idx] = orig_val + eps
        perturbed_x_plus = flat_x.reshape(x.shape)
        f_plus = func(perturbed_x_plus)

        # x - eps
        flat_x[idx] = orig_val - eps
        perturbed_x_minus = flat_x.reshape(x.shape)
        f_minus = func(perturbed_x_minus)

        # Restore
        flat_x[idx] = orig_val

        g_num = (f_plus - f_minus) / (2.0 * eps)
        g_ana = flat_grad_ana[idx]

        denom = max(float(abs(g_ana)), float(abs(g_num)), 1e-7)
        rel_err = float(abs(g_ana - g_num) / denom)

        if rel_err > max_rel_err:
            max_rel_err = rel_err

    passed = max_rel_err <= tol
    if not passed and raise_on_failure:
        raise GradientCheckFailedError(
            f"Numerical gradient check failed! Max relative error: {max_rel_err:.2e} > tolerance {tol:.2e}"
        )

    return passed, max_rel_err
