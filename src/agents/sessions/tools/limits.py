"""jarvis.agents.sessions.tools.limits — byte-limit helpers for session tool stderr/stdout tails.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/tools/limits.ts``.

Phase 6.10a — limits.

Tail storage is byte-bounded but decoded as
UTF-8, so truncation avoids splitting
multi-byte characters in display output.

Adaptations
-----------
- The OpenClaw source uses Node ``Buffer``
  for byte counting. The Python port uses
  :func:`jarvis_agent.truncate.utf8_byte_length`
  (the shared harness helper) + the
  canonical :func:`resolve_integer_option`
  from :mod:`src.agents.sessions.http_dispatcher`.
- The OpenClaw source's
  ``normalizePositiveLimit`` re-uses
  ``resolveIntegerOption(value, fallback, {min: 1})``.
  The Python port keeps the same shape via
  the Phase 6.8b :func:`resolve_integer_option`.
- The OpenClaw source's ``decodeUtf8TextTail``
  iterates the chars in reverse + keeps
  the byte budget. The Python port does
  the same iteration; the only difference
  is the byte-length lookup.
"""
from __future__ import annotations

from typing import Union

from ..http_dispatcher import resolve_integer_option
from jarvis_agent.truncate import utf8_byte_length


# ============================================================================
# Constants
# ============================================================================


#: Default stderr tail retained for long-running
#: session tools (64 KiB). Mirrors
#: ``SESSION_TOOL_STDERR_TAIL_BYTES``
#: (``limits.ts:15``).
SESSION_TOOL_STDERR_TAIL_BYTES: int = 64 * 1024


# ============================================================================
# Public API
# ============================================================================


def normalize_positive_limit(
    value: Union[int, float, None], fallback: int
) -> int:
    """Normalize an optional positive numeric
    limit to a finite integer. Mirrors
    ``normalizePositiveLimit``
    (``limits.ts:10-12``)."""
    return resolve_integer_option(value, fallback, {"min": 1})


def _decode_utf8_text_tail(text: str, max_bytes: int) -> str:
    """Return the last ``max_bytes`` of ``text``
    decoded as UTF-8, never splitting a
    multi-byte character. Mirrors
    ``decodeUtf8TextTail`` (``limits.ts:17-33``).
    """
    chars = list(text)
    kept: list[str] = []
    used = 0
    for ch in reversed(chars):
        char_bytes = utf8_byte_length(ch)
        if used + char_bytes > max_bytes:
            break
        kept.append(ch)
        used += char_bytes
    kept.reverse()
    return "".join(kept)


def append_bounded_text_tail(
    current: str,
    chunk: Union[str, bytes],
    max_bytes: int = SESSION_TOOL_STDERR_TAIL_BYTES,
) -> str:
    """Append ``chunk`` to ``current`` while
    retaining only the UTF-8-safe tail
    within ``max_bytes``. Mirrors
    ``appendBoundedTextTail``
    (``limits.ts:36-55``).

    The OpenClaw source accepts ``Buffer | str``
    for ``chunk``; the Python port accepts
    ``str | bytes`` (both decode cleanly).
    """
    effective = normalize_positive_limit(
        max_bytes, SESSION_TOOL_STDERR_TAIL_BYTES
    )
    if isinstance(chunk, bytes):
        chunk_text = chunk.decode("utf-8", errors="replace")
    else:
        chunk_text = chunk
    chunk_bytes = utf8_byte_length(chunk_text)
    if chunk_bytes >= effective:
        return _decode_utf8_text_tail(chunk_text, effective)

    current_bytes = utf8_byte_length(current)
    if current_bytes + chunk_bytes <= effective:
        return f"{current}{chunk_text}"

    current_tail_bytes = max(0, effective - chunk_bytes)
    if current_tail_bytes == 0:
        return _decode_utf8_text_tail(chunk_text, effective)
    # Trim the head of ``current`` to the
    # last ``current_tail_bytes`` bytes
    # (UTF-8-safe via ``_decode_utf8_text_tail``).
    current_tail = _decode_utf8_text_tail(current, current_tail_bytes)
    return _decode_utf8_text_tail(
        f"{current_tail}{chunk_text}", effective
    )


__all__ = [
    "SESSION_TOOL_STDERR_TAIL_BYTES",
    "append_bounded_text_tail",
    "normalize_positive_limit",
]
