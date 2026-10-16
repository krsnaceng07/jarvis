"""JARVIS media-understanding-core (shared core package - not a plugin).

Mirrors OpenClaw's ``extensions/media-understanding-core/`` shape:
OpenClaw ships this as a runtime package (no ``openclaw.plugin.json``),
so JARVIS mirrors that with ``pyproject.toml`` + ``__init__.py`` re-exports
from ``jarvis_sdk.media_understanding``.
"""

from __future__ import annotations

from jarvis_sdk.media_understanding import (
    AudioTranscriptionRequest,
    AudioTranscriptionResult,
    MediaUnderstandingProvider,
    transcribe_openai_compatible_audio,
)

__all__ = [
    "AudioTranscriptionRequest",
    "AudioTranscriptionResult",
    "MediaUnderstandingProvider",
    "transcribe_openai_compatible_audio",
]
