"""JARVIS Google Chat channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import GoogleChatPlugin, googlechat_plugin, entry
from .runtime import GoogleChatRuntime, get_googlechat_runtime

__all__ = [
    "GoogleChatPlugin",
    "googlechat_plugin",
    "entry",
    "GoogleChatRuntime",
    "get_googlechat_runtime",
]
