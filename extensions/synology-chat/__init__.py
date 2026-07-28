"""JARVIS Synology Chat channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import SynologyChatPlugin, synology_chat_plugin, entry
from .runtime import SynologyChatRuntime, get_synology_chat_runtime

__all__ = [
    "SynologyChatPlugin",
    "synology_chat_plugin",
    "entry",
    "SynologyChatRuntime",
    "get_synology_chat_runtime",
]
