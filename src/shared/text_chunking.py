"""jarvis.shared.text_chunking — soft-break text chunker.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text-chunking.ts``.
"""
from __future__ import annotations

import math
import re
from typing import Callable, List


def avoid_trailing_high_surrogate_break(text: str, _start: int, end: int) -> int:
    """Back off a slice end so it does not split a high+low surrogate pair.

    Mirrors the helper used by OpenClaw's chunker.
    """
    if end <= 0 or end >= len(text):
        return end
    # If char before end is a high surrogate (0xD800-0xDBFF) and end char is low (0xDC00-0xDFFF), back up.
    if 0xD800 <= ord(text[end - 1]) <= 0xDBFF and end < len(text) and 0xDC00 <= ord(text[end]) <= 0xDFFF:
        return end - 1
    return end


_WS_RE = re.compile(r"\s")


def chunk_text_by_break_resolver(
    text: str,
    limit: int,
    resolve_break_index: Callable[[str], int],
) -> List[str]:
    """Split ``text`` into bounded chunks using a caller-owned soft-break resolver.

    Mirrors :func:`chunkTextByBreakResolver` (``shared/text-chunking.ts``).
    """
    if not text:
        return []
    if limit <= 0 or len(text) <= limit:
        return [text]
    chunks: List[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        candidate = resolve_break_index(window)
        if isinstance(candidate, (int, float)) and math.isfinite(candidate) and 0 < candidate <= limit:
            break_idx = int(candidate)
        else:
            break_idx = limit
        safe_break_idx = avoid_trailing_high_surrogate_break(remaining, 0, break_idx)
        raw_chunk = remaining[:safe_break_idx]
        chunk = raw_chunk.rstrip()
        if chunk:
            chunks.append(chunk)
        # One matched separator is consumed at the boundary; adjacent whitespace
        # is trimmed before the next window.
        broke_on_separator = (
            safe_break_idx < len(remaining) and bool(_WS_RE.match(remaining[safe_break_idx]))
        )
        next_start = min(len(remaining), safe_break_idx + (1 if broke_on_separator else 0))
        remaining = remaining[next_start:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


__all__ = ["chunk_text_by_break_resolver", "avoid_trailing_high_surrogate_break"]
