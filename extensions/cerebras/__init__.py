"""JARVIS Cerebras provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import CerebrasProvider, cerebras_provider, entry

__all__ = [
    "CerebrasProvider",
    "cerebras_provider",
    "entry",
]
