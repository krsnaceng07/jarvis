"""JARVIS vLLM provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import vLLMProvider, vllm_provider, entry

__all__ = [
    "vLLMProvider",
    "vllm_provider",
    "entry",
]
