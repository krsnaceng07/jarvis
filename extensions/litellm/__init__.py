"""JARVIS LiteLLM provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import LiteLLMProvider, litellm_provider, entry

__all__ = [
    "LiteLLMProvider",
    "litellm_provider",
    "entry",
]
