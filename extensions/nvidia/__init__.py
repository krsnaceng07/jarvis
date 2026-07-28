"""JARVIS NVIDIA NIM provider extension (Phase 5.15 minimum scaffold)."""
from __future__ import annotations

from .plugin import NVIDIANIMProvider, nvidia_provider, entry

__all__ = [
    "NVIDIANIMProvider",
    "nvidia_provider",
    "entry",
]
