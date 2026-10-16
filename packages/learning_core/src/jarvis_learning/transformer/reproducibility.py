"""Reproducibility utilities for deterministic model initialization and training."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator
import numpy as np


def get_deterministic_rng(seed: int = 42) -> np.random.Generator:
    """Creates a deterministic PCG64 random number generator."""
    return np.random.default_rng(seed)


@contextmanager
def reproducible_scope(seed: int = 42) -> Generator[np.random.Generator, None, None]:
    """Context manager setting a deterministic generator scope."""
    rng = np.random.default_rng(seed)
    yield rng
