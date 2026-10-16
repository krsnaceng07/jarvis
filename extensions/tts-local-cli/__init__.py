"""JARVIS TTS Local CLI infra extension (Phase 5.15 minimum scaffold)."""

from __future__ import annotations

from .plugin import TTSLocalCLIPlugin, tts_local_cli_plugin, entry

__all__ = [
    "TTSLocalCLIPlugin",
    "tts_local_cli_plugin",
    "entry",
]
