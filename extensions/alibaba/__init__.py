"""JARVIS Alibaba Qwen provider extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import AlibabaQwenProvider, alibaba_provider, entry

__all__ = [
    "AlibabaQwenProvider",
    "alibaba_provider",
    "entry",
]
