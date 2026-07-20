"""jarvis_sdk.text_utility — UTF-16-safe string utilities.

OpenClaw parity: mirrors ``openclaw/plugin-sdk/text-utility-runtime``'s
``truncateUtf16Safe``.

Used by ``memory-lancedb`` to safely truncate strings for
embedding input (which has a max token limit, mapped to char
count via the OpenClaw ``CJK_CHARS_PER_TOKEN_ESTIMATE`` constant).

Architecture
============
Python's ``str`` is already a sequence of Unicode code points,
not UTF-16 code units — but the OpenClaw SDK names the helper
``truncateUtf16Safe`` because the JS side operates on
``string.length`` (UTF-16 code units). For the Python port we
treat UTF-16 length as ``len(string)`` for the BMP range
(``<= 0xFFFF``) and ``+1`` per supplementary code point
(``> 0xFFFF``, encoded as 2 code units in UTF-16). This
matches the JS interpretation for the common case while
preserving correctness for emoji and supplementary CJK.

Parity
======
- ``truncate_utf16_safe(s, max_units)`` returns ``s`` unchanged
  if its UTF-16 length <= max_units; otherwise truncates so the
  result's UTF-16 length is <= max_units. Never returns a
  string that splits a surrogate pair.
"""

from __future__ import annotations


def utf16_length(s: str) -> int:
    """Return the UTF-16 code unit length of ``s``.

    BMP code points (``<= 0xFFFF``) take 1 unit; supplementary
    code points (most emoji + CJK extensions) take 2 units.
    Matches JavaScript's ``string.length`` semantics.
    """
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in s)


def truncate_utf16_safe(s: str, max_units: int) -> str:
    """Truncate ``s`` so its UTF-16 length is <= ``max_units``.

    Never splits a surrogate pair: if the truncation would land
    between the two halves of a supplementary code point, we
    back off by one code point.

    Mirrors ``openclaw/plugin-sdk/text-utility-runtime``'s
    ``truncateUtf16Safe``.
    """
    if max_units < 0:
        raise ValueError("max_units must be >= 0")
    if utf16_length(s) <= max_units:
        return s

    # Truncate by code points, tracking UTF-16 length.
    out: list[str] = []
    used = 0
    for ch in s:
        cost = 2 if ord(ch) > 0xFFFF else 1
        if used + cost > max_units:
            break
        out.append(ch)
        used += cost
    return "".join(out)


__all__ = ["truncate_utf16_safe", "utf16_length"]
