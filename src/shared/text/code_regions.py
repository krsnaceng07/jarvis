"""jarvis.shared.text.code_regions — Markdown code region finder.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/code-regions.ts``.
"""
from __future__ import annotations

import re
from typing import List, TypedDict


class CodeRegion(TypedDict):
    start: int
    end: int


#: Fenced code block (``` or ~~~) with optional info string after the fence.
_FENCED_RE = re.compile(r"(^|\n)(```|~~~)[^\n]*\n[\s\S]*?(?:\n\2|$)", re.MULTILINE)
#: Inline code span (one or more backticks).
_INLINE_RE = re.compile(r"`+[^`]+`+")


def find_code_regions(text: str) -> List[CodeRegion]:
    """Find fenced and inline Markdown code regions in ``text``.

    Mirrors :func:`findCodeRegions` (``shared/text/code-regions.ts``).
    """
    if not isinstance(text, str):
        return []
    regions: List[CodeRegion] = []
    for match in _FENCED_RE.finditer(text):
        prefix_len = len(match.group(1))
        start = (match.start() or 0) + prefix_len
        regions.append({"start": start, "end": start + len(match.group(0)) - prefix_len})
    for match in _INLINE_RE.finditer(text):
        start = match.start() or 0
        end = start + len(match.group(0))
        inside_fenced = any(start >= r["start"] and end <= r["end"] for r in regions)
        if not inside_fenced:
            regions.append({"start": start, "end": end})
    regions.sort(key=lambda r: r["start"])
    return regions


def is_inside_code(pos: int, regions: List[CodeRegion]) -> bool:
    """Return whether ``pos`` falls inside one of the discovered code regions.

    Mirrors :func:`isInsideCode` (``shared/text/code-regions.ts``).
    """
    return any(pos >= r["start"] and pos < r["end"] for r in regions)


__all__ = ["CodeRegion", "find_code_regions", "is_inside_code"]
