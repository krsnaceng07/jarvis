"""jarvis.shared.levenshtein_distance — Levenshtein edit distance.

OpenClaw parity: mirrors ``openclaw-main/src/shared/levenshtein-distance.ts``.
"""
from __future__ import annotations


def levenshtein_distance(left: str, right: str) -> int:
    """Compute the Levenshtein edit distance between two strings.

    Mirrors :func:`levenshteinDistance` (``shared/levenshtein-distance.ts``).
    """
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    current = [0] * (len(right) + 1)
    for i, ch_l in enumerate(left):
        current[0] = i + 1
        for j, ch_r in enumerate(right):
            cost = 0 if ch_l == ch_r else 1
            current[j + 1] = min(
                current[j] + 1,
                previous[j + 1] + 1,
                previous[j] + cost,
            )
        previous, current = current, previous
    return previous[len(right)]


__all__ = ["levenshtein_distance"]
