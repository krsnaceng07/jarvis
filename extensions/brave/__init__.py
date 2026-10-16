"""JARVIS Brave infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import BravePlugin, brave_plugin, entry

__all__ = [
    "BravePlugin",
    "brave_plugin",
    "entry",
]
