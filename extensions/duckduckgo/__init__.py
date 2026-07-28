"""JARVIS DuckDuckGo infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import DuckDuckGoPlugin, duckduckgo_plugin, entry

__all__ = [
    "DuckDuckGoPlugin",
    "duckduckgo_plugin",
    "entry",
]
