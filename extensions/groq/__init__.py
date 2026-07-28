"""JARVIS groq provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import GroqProvider, groq_provider, entry

__all__ = [
    "GroqProvider",
    "groq_provider",
    "entry",
]
