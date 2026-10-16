"""JARVIS OpenRouter provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import OpenRouterProvider, openrouter_provider, entry

__all__ = [
    "OpenRouterProvider",
    "openrouter_provider",
    "entry",
]
