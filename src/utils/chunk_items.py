"""jarvis.utils.chunk_items — split items into fixed-size chunks.

OpenClaw parity: mirrors ``openclaw-main/src/utils/chunk-items.ts``.

Public surface:

- :func:`chunk_items`
"""
from __future__ import annotations

from typing import List, Sequence, TypeVar

T = TypeVar("T")


def chunk_items(items: Sequence[T], size: int) -> List[List[T]]:
    """Split ``items`` into fixed-size chunks, preserving order.

    Returns a single-element list containing all items when ``size <= 0``.

    Mirrors :func:`chunkItems` (``utils/chunk-items.ts``).
    """
    if size <= 0:
        return [list(items)]
    rows: List[List[T]] = []
    for i in range(0, len(items), size):
        rows.append(list(items[i:i + size]))
    return rows


__all__ = ["chunk_items"]
