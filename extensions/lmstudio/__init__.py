"""JARVIS LM Studio provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import LMStudioProvider, lmstudio_provider, entry

__all__ = [
    "LMStudioProvider",
    "lmstudio_provider",
    "entry",
]
