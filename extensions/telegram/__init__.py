"""Telegram extension compatibility package root.

This package re-exports the OpenClaw-style entry points the host/tests
import directly from ``extensions.telegram``.
"""

from __future__ import annotations

from .plugin import TelegramChannelPlugin, entry, plugin, _register
from . import runtime

__all__ = [
    "TelegramChannelPlugin",
    "entry",
    "_register",
    "plugin",
    "runtime",
]
