"""jarvis_sdk.memory_host_cjk_chars — CJK-aware char counting helpers.

OpenClaw parity: mirrors
``openclaw/src/utils/cjk-chars.ts`` (~80 LOC).
Helpers for accurate token estimation across scripts. Latin
text averages ~1 token per 4 chars; CJK averages ~1 token
per char. The ``estimateStringChars`` helper inflates the
character count of CJK text so the standard
``chars / CHARS_PER_TOKEN_ESTIMATE`` formula yields an
accurate token estimate.

Public API:
- ``CHARS_PER_TOKEN_ESTIMATE = 4`` (Latin baseline).
- ``estimate_string_chars(text)`` — adjusted char count.
- ``estimate_tokens_from_chars(chars)`` — round-up token
  estimate.
"""
from __future__ import annotations

import re

#: Mirrors OpenClaw's ``CHARS_PER_TOKEN_ESTIMATE = 4``.
#: Latin text averages 1 token per 4 chars; CJK averages 1
#: token per char. Used as the divisor for token estimates.
CHARS_PER_TOKEN_ESTIMATE: int = 4

#: Mirrors OpenClaw's ``NON_LATIN_RE``. Matches the CJK
#: ranges (Unified Ideographs, Extensions A/B, Compatibility,
#: Hangul Syllables, Hiragana, Katakana, East Asian fullwidth)
#: and CJK Extension B+ (U+20000-U+2FA1F). Use ``re.UNICODE``
#: so the astral-range match works.
_NON_LATIN_RE: re.Pattern[str] = re.compile(
    r"["
    r"\u2E80-\u9FFF"
    r"\uA000-\uA4FF"
    r"\uAC00-\uD7AF"
    r"\uF900-\uFAFF"
    r"\uFF01-\uFF60"
    r"\uFFE0-\uFFE6"
    r"\U00020000-\U0002FA1F"
    r"]",
    re.UNICODE,
)

#: Mirrors OpenClaw's ``CJK_SURROGATE_HIGH_RE``. Matches
#: surrogate pairs whose code point is in CJK Extension B+
#: (U+20000-U+2FA1F). High-surrogate range D840-D87E.
_CJK_SURROGATE_HIGH_RE: re.Pattern[str] = re.compile(
    r"[\uD840-\uD87E][\uDC00-\uDFFF]"
)


def _count_code_points(text: str, non_latin_count: int) -> int:
    """Count code points, adjusting for CJK surrogate pairs.

    Mirrors OpenClaw's ``countCodePoints`` helper. For text
    without astral-range CJK characters, returns
    ``len(text)`` unchanged.
    """
    if non_latin_count == 0:
        return len(text)
    cjk_surrogates = len(_CJK_SURROGATE_HIGH_RE.findall(text))
    return len(text) - cjk_surrogates


def estimate_string_chars(text: str) -> int:
    """Return an adjusted char count that accounts for non-Latin scripts.

    Mirrors OpenClaw's ``estimateStringChars``. Each non-Latin
    character is counted as ``CHARS_PER_TOKEN_ESTIMATE`` chars
    so that ``chars / CHARS_PER_TOKEN_ESTIMATE`` yields an
    accurate token estimate for any script.

    For pure ASCII / Latin text, the return value equals
    ``len(text)``.
    """
    if not text:
        return 0
    non_latin_count = len(_NON_LATIN_RE.findall(text))
    code_point_length = _count_code_points(text, non_latin_count)
    return code_point_length + non_latin_count * (CHARS_PER_TOKEN_ESTIMATE - 1)


def estimate_tokens_from_chars(chars: int) -> int:
    """Estimate token count from a raw char count.

    Mirrors OpenClaw's ``estimateTokensFromChars``. Uses
    ``ceil(max(0, chars) / CHARS_PER_TOKEN_ESTIMATE)``.
    """
    if chars <= 0:
        return 0
    return (chars + CHARS_PER_TOKEN_ESTIMATE - 1) // CHARS_PER_TOKEN_ESTIMATE


__all__ = [
    "CHARS_PER_TOKEN_ESTIMATE",
    "estimate_string_chars",
    "estimate_tokens_from_chars",
]
