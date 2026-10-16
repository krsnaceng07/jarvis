"""JARVIS MS Teams provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import MSTeamsProvider, msteams_provider, entry

__all__ = [
    "MSTeamsProvider",
    "msteams_provider",
    "entry",
]
