"""JARVIS Matrix channel extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import MatrixPlugin, matrix_plugin, entry
from .runtime import MatrixRuntime, get_matrix_runtime

__all__ = [
    "MatrixPlugin",
    "matrix_plugin",
    "entry",
    "MatrixRuntime",
    "get_matrix_runtime",
]
