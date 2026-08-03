"""jarvis.shared.text.join_segments — optional text segment joiners.

OpenClaw parity: mirrors ``openclaw-main/src/shared/text/join-segments.ts``.
"""
from __future__ import annotations

from typing import Iterable, Optional


def concat_optional_text_segments(params: dict) -> Optional[str]:
    """Concatenate two optional text blocks, preserving the right block's
    explicit empty string.

    Mirrors :func:`concatOptionalTextSegments`
    (``shared/text/join-segments.ts``).
    """
    separator = params.get("separator") or "\n\n"
    left = params.get("left")
    right = params.get("right")
    if left and right:
        return f"{left}{separator}{right}"
    return right if right is not None else left


def join_present_text_segments(
    segments: Iterable[object],
    *,
    separator: str = "\n\n",
    trim: bool = False,
) -> Optional[str]:
    """Join non-empty string segments, optionally trimming each before
    presence checks.

    Mirrors :func:`joinPresentTextSegments``
    (``shared/text/join-segments.ts``).
    """
    values = []
    for segment in segments:
        if not isinstance(segment, str):
            continue
        normalized = segment.strip() if trim else segment
        if not normalized:
            continue
        values.append(normalized)
    if not values:
        return None
    return separator.join(values)


__all__ = [
    "concat_optional_text_segments",
    "join_present_text_segments",
]
