"""JARVIS Ollama provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import OllamaProvider, ollama_provider, entry

__all__ = [
    "OllamaProvider",
    "ollama_provider",
    "entry",
]
