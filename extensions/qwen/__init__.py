"""JARVIS Qwen provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import QwenProvider, qwen_provider, entry

__all__ = [
    "QwenProvider",
    "qwen_provider",
    "entry",
]
