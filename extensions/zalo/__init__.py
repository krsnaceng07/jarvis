"""JARVIS Zalo channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import ZaloPlugin, zalo_plugin, entry
from .runtime import ZaloRuntime, get_zalo_runtime

__all__ = [
    "ZaloPlugin",
    "zalo_plugin",
    "entry",
    "ZaloRuntime",
    "get_zalo_runtime",
]
