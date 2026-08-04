"""jarvis.config.ambient_transcript_watermark — ambient transcript watermark.

OpenClaw parity: mirrors
``openclaw-main/src/config/ambient-transcript-watermark.ts``.

Focused minimal port: thin facade. The ambient watermark marker is
emitted into transcripts that come from ambient transcription sources
(sleep, push-to-talk) and lets downstream consumers recognize them.
The Python port exposes the marker constant + a writer helper.
"""
from __future__ import annotations

from typing import Any, Optional


#: Canonical ambient-transcript watermark prefix.
AMBIENT_TRANSCRIPT_WATERMARK = "[ambient]"


def is_ambient_transcript_marker(value: Any) -> bool:
    """Return whether ``value`` is the ambient transcript marker."""
    return isinstance(value, str) and value.startswith(AMBIENT_TRANSCRIPT_WATERMARK)


def stamp_ambient_transcript_marker(text: Any) -> Optional[str]:
    """Prefix ``text`` with the ambient watermark; returns None for non-strings."""
    if not isinstance(text, str):
        return None
    if is_ambient_transcript_marker(text):
        return text
    return f"{AMBIENT_TRANSCRIPT_WATERMARK} {text}"


def strip_ambient_transcript_marker(text: Any) -> Optional[str]:
    """Remove the ambient watermark from ``text``; returns None for non-strings."""
    if not isinstance(text, str):
        return None
    if not is_ambient_transcript_marker(text):
        return text
    return text[len(AMBIENT_TRANSCRIPT_WATERMARK):].lstrip()


__all__ = [
    "AMBIENT_TRANSCRIPT_WATERMARK",
    "is_ambient_transcript_marker",
    "stamp_ambient_transcript_marker",
    "strip_ambient_transcript_marker",
]
