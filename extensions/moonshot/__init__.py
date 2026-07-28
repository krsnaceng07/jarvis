"""JARVIS Moonshot provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import MoonshotProvider, moonshot_provider, entry

__all__ = [
    "MoonshotProvider",
    "moonshot_provider",
    "entry",
]
