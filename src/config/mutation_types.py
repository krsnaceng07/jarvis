"""jarvis.config.mutation_types — config mutation base type.

OpenClaw parity: mirrors ``openclaw-main/src/config/mutation-types.ts``.
"""
from __future__ import annotations

#: Selects whether a mutation starts from the runtime or source config shape.
ConfigMutationBase = str  # "runtime" | "source"


__all__ = ["ConfigMutationBase"]
