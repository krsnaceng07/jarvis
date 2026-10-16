"""JARVIS llama.cpp provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import llamacppProvider, llama_cpp_provider, entry

__all__ = [
    "llamacppProvider",
    "llama_cpp_provider",
    "entry",
]
