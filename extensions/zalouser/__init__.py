"""JARVIS Zalo User channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import ZaloUserPlugin, zalouser_plugin, entry
from .runtime import ZaloUserRuntime, get_zalouser_runtime

__all__ = [
    "ZaloUserPlugin",
    "zalouser_plugin",
    "entry",
    "ZaloUserRuntime",
    "get_zalouser_runtime",
]
