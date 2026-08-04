"""jarvis.config.mutation_conflict — config-write optimistic-snapshot conflict error.

OpenClaw parity: mirrors ``openclaw-main/src/config/mutation-conflict.ts``.
"""
from __future__ import annotations

from typing import Optional


class ConfigMutationConflictError(Exception):
    """Raised when a config write loses an optimistic snapshot race.

    Mirrors :class:`ConfigMutationConflictError`
    (``shared/config/mutation-conflict.ts`).
    """

    currentHash: Optional[str]
    retryable: bool

    def __init__(
        self,
        message: str,
        *,
        current_hash: Optional[str] = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.name = "ConfigMutationConflictError"
        self.currentHash = current_hash
        self.retryable = retryable


__all__ = ["ConfigMutationConflictError"]
