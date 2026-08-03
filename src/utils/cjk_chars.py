"""jarvis.utils.cjk_chars — CJK-aware character counting for token estimation.

OpenClaw parity: mirrors ``openclaw-main/src/utils/cjk-chars.ts``.

Public surface:

- :data:`CHARS_PER_TOKEN_ESTIMATE`
- :func:`estimate_string_chars`
- :func:`estimate_tokens_from_chars`
"""
from __future__ import annotations

import re
from typing import Optional


CHARS_PER_TOKEN_ESTIMATE = 4

#: Matches CJK Unified Ideographs, Hangul, Hiragana, Katakana, etc.
_NON_LATIN_RE = re.compile(
    "["
    "\u2E80-\u9FFF"
    "\uA000-\uA4FF"
    "\uAC00-\uD7AF"
    "\uF900-\uFAFF"
    "\uFF01-\uFF60"
    "\uFFE0-\uFFE6"
    "\U00020000-\U0002FA1F"
    "]",
    re.UNICODE,
)

#: CJK Extension B+ surrogate pairs.
_CJK_SURROGATE_HIGH_RE = re.compile("[\uD840-\uD87E][\uDC00-\uDFFF]")


def _count_code_points(text: str, non_latin_count: int) -> int:
    if non_latin_count == 0:
        return len(text)
    cjk_surrogates = len(_CJK_SURROGATE_HIGH_RE.findall(text))
    return len(text) - cjk_surrogates


def estimate_string_chars(text: str) -> int:
    """Adjusted character length that accounts for non-Latin (CJK, etc.) characters.

    Mirrors :func:`estimateStringChars` (``utils/cjk-chars.ts``).
    """
    if not text:
        return 0
    non_latin_count = len(_NON_LATIN_RE.findall(text))
    code_point_length = _count_code_points(text, non_latin_count)
    return code_point_length + non_latin_count * (CHARS_PER_TOKEN_ESTIMATE - 1)


def estimate_tokens_from_chars(chars: int) -> int:
    """Estimate the number of tokens from a raw character count.

    Mirrors :func:`estimateTokensFromChars` (``utils/cjk-chars.ts``).
    """
    safe = max(0, int(chars or 0))
    return -(-safe // CHARS_PER_TOKEN_ESTIMATE)  # ceil division


__all__ = [
    "CHARS_PER_TOKEN_ESTIMATE",
    "estimate_string_chars",
    "estimate_tokens_from_chars",
]
