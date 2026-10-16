"""Gradient manipulation utilities and global norm clipping."""

from __future__ import annotations

from typing import Any
import numpy as np


def collect_leaf_arrays(grad_structure: Any) -> list[np.ndarray]:
    """Recursively collects all leaf numpy arrays from a nested dict/list structure."""
    arrays: list[np.ndarray] = []
    if isinstance(grad_structure, np.ndarray):
        arrays.append(grad_structure)
    elif isinstance(grad_structure, dict):
        for v in grad_structure.values():
            arrays.extend(collect_leaf_arrays(v))
    elif isinstance(grad_structure, (list, tuple)):
        for item in grad_structure:
            arrays.extend(collect_leaf_arrays(item))
    return arrays


def compute_grad_norm(grad_structure: Any) -> float:
    """Computes global L2 Frobenius norm across all gradient tensors."""
    leafs = collect_leaf_arrays(grad_structure)
    if not leafs:
        return 0.0
    sum_sq = sum(float(np.sum(arr**2)) for arr in leafs)
    return float(np.sqrt(sum_sq))


def scale_gradients(grad_structure: Any, scale: float) -> Any:
    """Recursively scales all gradient arrays in-place or returns scaled copy."""
    if isinstance(grad_structure, np.ndarray):
        return grad_structure * scale
    elif isinstance(grad_structure, dict):
        return {k: scale_gradients(v, scale) for k, v in grad_structure.items()}
    elif isinstance(grad_structure, list):
        return [scale_gradients(item, scale) for item in grad_structure]
    elif isinstance(grad_structure, tuple):
        return tuple(scale_gradients(item, scale) for item in grad_structure)
    return grad_structure


def clip_grad_norm(grad_structure: Any, max_norm: float) -> tuple[Any, float]:
    """Clips global gradient norm to max_norm.

    Returns:
        (clipped_grad_structure, total_norm)
    """
    total_norm = compute_grad_norm(grad_structure)
    if total_norm > max_norm and max_norm > 0.0:
        scale = max_norm / (total_norm + 1e-6)
        clipped = scale_gradients(grad_structure, scale)
        return clipped, total_norm
    return grad_structure, total_norm
