"""JARVIS Azure Speech provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import AzureSpeechProvider, azure_speech_provider, entry

__all__ = [
    "AzureSpeechProvider",
    "azure_speech_provider",
    "entry",
]
