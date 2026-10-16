"""JARVIS mistral provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import MistralProvider, mistral_provider, entry

__all__ = [
    "MistralProvider",
    "mistral_provider",
    "entry",
]
