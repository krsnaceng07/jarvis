"""JARVIS Signal channel extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import SignalPlugin, signal_plugin, entry
from .runtime import SignalRuntime, get_signal_runtime

__all__ = [
    "SignalPlugin",
    "signal_plugin",
    "entry",
    "SignalRuntime",
    "get_signal_runtime",
]
