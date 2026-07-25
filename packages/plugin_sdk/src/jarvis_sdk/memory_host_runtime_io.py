"""jarvis_sdk.memory_host_runtime_io — narrow IO/runtime facade for memory host.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/host/openclaw-runtime-io.ts``
(narrow re-export facade).
Re-exports the subset of runtime helpers the memory host
needs: ``CHARS_PER_TOKEN_ESTIMATE``, ``estimateStringChars``,
``truncateUtf16Safe``, ``detectMime``.

Key port decisions:
- ``CHARS_PER_TOKEN_ESTIMATE`` / ``estimateStringChars`` come
  from ``memory_host_cjk_chars`` (port of OpenClaw's
  ``src/utils/cjk-chars.ts``).
- ``truncateUtf16Safe`` comes from ``text_utility`` (already
  ported for memory-lancedb).
- ``detectMime`` is a small stdlib-backed helper — no
  external MIME database required for the memory host's
  use case (image / audio / markdown).
"""
from __future__ import annotations

from pathlib import Path

from .memory_host_cjk_chars import (
    CHARS_PER_TOKEN_ESTIMATE,
    estimate_string_chars,
)
from jarvis_normalization_core.text_utility import truncate_utf16_safe


def detect_mime(
    *,
    buffer: bytes,
    file_path: str,
) -> str | None:
    """Detect a MIME type from a buffer + file path.

    Mirrors OpenClaw's ``detectMime`` shape (``@openclaw/media-core/mime``).
    The Python port uses a small built-in extension table —
    no external MIME database required for the memory host
    (image / audio / markdown / text).
    """
    ext = Path(file_path).suffix.lower()
    by_ext: dict[str, str] = {
        # Markdown + text
        ".md": "text/markdown",
        ".markdown": "text/markdown",
        ".txt": "text/plain",
        # Image
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".heic": "image/heic",
        ".heif": "image/heif",
        # Audio
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".ogg": "audio/ogg",
        ".opus": "audio/opus",
        ".m4a": "audio/mp4",
        ".m2a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
    }
    if ext in by_ext:
        return by_ext[ext]
    # Best-effort magic-byte sniffing for the most common shapes.
    if buffer.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if buffer.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if buffer.startswith(b"GIF87a") or buffer.startswith(b"GIF89a"):
        return "image/gif"
    if buffer.startswith(b"RIFF") and buffer[8:12] == b"WEBP":
        return "image/webp"
    if buffer.startswith(b"ID3") or buffer.startswith(b"\xff\xfb"):
        return "audio/mpeg"
    if buffer.startswith(b"OggS"):
        return "audio/ogg"
    if buffer.startswith(b"fLaC"):
        return "audio/flac"
    return None


__all__ = [
    "CHARS_PER_TOKEN_ESTIMATE",
    "estimate_string_chars",
    "truncate_utf16_safe",
    "detect_mime",
]
