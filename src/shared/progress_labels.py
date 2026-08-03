"""jarvis.shared.progress_labels — progress draft label selector.

OpenClaw parity: mirrors ``openclaw-main/src/shared/progress-labels.ts``.
"""
from __future__ import annotations

from typing import Callable, List, Optional

#: Default progress draft labels.
DEFAULT_PROGRESS_DRAFT_LABELS: List[str] = ["Working"]


def _hash_progress_seed(seed: str) -> int:
    h = 2166136261
    for ch in seed:
        h ^= ord(ch)
        h = (h * 16777619) & 0xFFFFFFFF
    return h


def select_progress_label(params: dict) -> Optional[str]:
    """Pick a progress label deterministically by seed or pseudo-randomly.

    Mirrors :func:`selectProgressLabel` (``shared/progress-labels.ts``).
    """
    provided = params.get("labels")
    labels = provided if provided is not None else DEFAULT_PROGRESS_DRAFT_LABELS
    if len(labels) == 0:
        return None
    seed = params.get("seed")
    rng = params.get("random")
    if isinstance(seed, str) and len(seed) > 0:
        index = _hash_progress_seed(seed) % len(labels)
    else:
        n = max(0.0, min(0.999999, rng() if callable(rng) else 0.0))
        index = int(n * len(labels))
    if 0 <= index < len(labels):
        return labels[index]
    return labels[0]


__all__ = ["DEFAULT_PROGRESS_DRAFT_LABELS", "select_progress_label"]
