"""Deterministic normalization for structured system-prompt sections.

OpenClaw parity: ``normalizeStructuredPromptSection`` in
``packages/ai/src/utils/prompt-cache-stability.ts`` — sanitize lone
surrogates, normalize CRLF/CR to LF, strip trailing spaces/tabs per line,
then trim the whole block so prompt-cache keys stay stable.
"""
from __future__ import annotations

__all__ = ["normalize_structured_prompt_section", "sanitize_surrogates"]

_REPLACEMENT = "\ufffd"


def sanitize_surrogates(text: str) -> str:
    """Replace unpaired UTF-16 surrogate code points with U+FFFD."""
    if not any("\ud800" <= ch <= "\udfff" for ch in text):
        return text
    return "".join(
        _REPLACEMENT if "\ud800" <= ch <= "\udfff" else ch for ch in text
    )


def normalize_structured_prompt_section(text: str) -> str:
    sanitized = sanitize_surrogates(text)
    normalized = sanitized.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip(" \t") for line in normalized.split("\n")]
    return "\n".join(lines).strip()
