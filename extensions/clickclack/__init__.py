"""JARVIS ClickClack channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import ClickClackPlugin, clickclack_plugin, entry
from .runtime import ClickClackRuntime, get_clickclack_runtime

__all__ = [
    "ClickClackPlugin",
    "clickclack_plugin",
    "entry",
    "ClickClackRuntime",
    "get_clickclack_runtime",
]
