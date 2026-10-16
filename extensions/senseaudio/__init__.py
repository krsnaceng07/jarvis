"""JARVIS SenseAudio media-understanding provider extension (Phase 5.15 real surface port)."""

from __future__ import annotations

from .media_understanding_provider import (
    DEFAULT_SENSEAUDIO_AUDIO_BASE_URL,
    DEFAULT_SENSEAUDIO_AUDIO_MODEL,
    senseaudio_media_understanding_provider,
    transcribe_senseaudio_audio,
)
from .plugin import SenseAudioPlugin, senseaudio_plugin, entry

__all__ = [
    "DEFAULT_SENSEAUDIO_AUDIO_BASE_URL",
    "DEFAULT_SENSEAUDIO_AUDIO_MODEL",
    "SenseAudioPlugin",
    "entry",
    "senseaudio_media_understanding_provider",
    "senseaudio_plugin",
    "transcribe_senseaudio_audio",
]
