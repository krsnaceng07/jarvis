"""JARVIS iMessage channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import iMessagePlugin, imessage_plugin, entry
from .runtime import iMessageRuntime, get_imessage_runtime

__all__ = [
    "iMessagePlugin",
    "imessage_plugin",
    "entry",
    "iMessageRuntime",
    "get_imessage_runtime",
]
