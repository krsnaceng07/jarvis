"""jarvis.shared.human_list — human-readable disjunction formatter.

OpenClaw parity: mirrors ``openclaw-main/src/shared/human-list.ts``.
"""
from __future__ import annotations

from typing import Sequence


def format_human_list(values: Sequence[str]) -> str:
    """Format a short human-readable disjunction such as ``"A, B, or C"``.

    Mirrors :func:`formatHumanList` (``shared/human-list.ts``).
    """
    if len(values) == 0:
        return ""
    if len(values) == 1:
        return values[0]
    if len(values) == 2:
        return f"{values[0]} or {values[1]}"
    return f"{', '.join(values[:-1])}, or {values[-1]}"


__all__ = ["format_human_list"]
