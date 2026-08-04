"""jarvis.config.types_commitments — commitment feature config types.

OpenClaw parity: mirrors ``openclaw-main/src/config/types.commitments.ts``.
"""
from __future__ import annotations

from typing import TypedDict


class CommitmentsConfig(TypedDict, total=False):
    """Config for inferred follow-up extraction, storage, and delivery."""

    enabled: bool
    maxPerDay: int


__all__ = ["CommitmentsConfig"]
