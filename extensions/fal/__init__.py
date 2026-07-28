"""JARVIS FAL provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import FALProvider, fal_provider, entry

__all__ = [
    "FALProvider",
    "fal_provider",
    "entry",
]
