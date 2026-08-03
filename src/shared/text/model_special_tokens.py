"""jarvis.shared.text.model_special_tokens — strip leaked model control tokens.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/model-special-tokens.ts``.

Removes leaked model control tokens like ``<|assistant|>`` or full-width
pipe variants. Code examples are preserved; remove this when providers
stop emitting these tokens.
"""
from __future__ import annotations

import re
from typing import List

from .code_regions import CodeRegion, find_code_regions, is_inside_code

#: Match both ASCII pipe <|...|> and full-width pipe variants (U+FF5C).
_MODEL_SPECIAL_TOKEN_RE = re.compile(r"<[|\uff5c][^|\uff5c]*[|\uff5c]>")


def _overlaps_code_region(start: int, end: int, code_regions: List[CodeRegion]) -> bool:
    return any(start < r["end"] and end > r["start"] for r in code_regions)


def _should_insert_separator(before: object, after: object) -> bool:
    if not (isinstance(before, str) and isinstance(after, str)):
        return False
    if not (before and after):
        return False
    if re.search(r"\s", before) or re.search(r"\s", after):
        return False
    return True


def strip_model_special_tokens(text: str) -> str:
    """Strip leaked model control tokens while preserving code regions.

    Mirrors :func:`stripModelSpecialTokens`
    (``shared/text/model-special-tokens.ts``).
    """
    if not text:
        return text
    if not _MODEL_SPECIAL_TOKEN_RE.search(text):
        return text

    code_regions = find_code_regions(text)
    out_parts: List[str] = []
    cursor = 0
    for match in _MODEL_SPECIAL_TOKEN_RE.finditer(text):
        matched = match.group(0)
        start = match.start() or 0
        end = start + len(matched)
        out_parts.append(text[cursor:start])
        if is_inside_code(start, code_regions) or _overlaps_code_region(start, end, code_regions):
            out_parts.append(matched)
        elif _should_insert_separator(text[start - 1] if start > 0 else "", text[end] if end < len(text) else ""):
            out_parts.append(" ")
        cursor = end
    out_parts.append(text[cursor:])
    return "".join(out_parts)


__all__ = ["strip_model_special_tokens"]
