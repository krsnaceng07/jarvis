"""JARVIS SearXNG infra extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import SearXNGPlugin, searxng_plugin, entry

__all__ = [
    "SearXNGPlugin",
    "searxng_plugin",
    "entry",
]
