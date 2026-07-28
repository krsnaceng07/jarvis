"""JARVIS huggingface provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import HuggingfaceProvider, huggingface_provider, entry

__all__ = [
    "HuggingfaceProvider",
    "huggingface_provider",
    "entry",
]
