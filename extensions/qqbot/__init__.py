"""JARVIS QQ Bot channel extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import QQBotPlugin, qqbot_plugin, entry
from .runtime import QQBotRuntime, get_qqbot_runtime

__all__ = [
    "QQBotPlugin",
    "qqbot_plugin",
    "entry",
    "QQBotRuntime",
    "get_qqbot_runtime",
]
