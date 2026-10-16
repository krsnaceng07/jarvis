"""JARVIS Voice Call infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import VoiceCallPlugin, voice_call_plugin, entry

__all__ = [
    "VoiceCallPlugin",
    "voice_call_plugin",
    "entry",
]
