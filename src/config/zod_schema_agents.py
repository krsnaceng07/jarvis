"""jarvis.config.zod_schema_agents — agent-related Zod schema fragments.

OpenClaw parity: mirrors ``openclaw-main/src/config/zod-schema.agents.ts``.
"""
from __future__ import annotations

from typing import Any, Literal


#: Agent list config schema.
AgentsSchema: Any = None  # z.object({defaults?, list?}).strict().optional()

#: Bindings config schema (route + ACP variants).
BindingsSchema: Any = None  # z.array(z.union([RouteBinding, AcpBinding])).optional()

#: Broadcast config schema.
BroadcastSchema: Any = None  # z.object({strategy?}).catchall(z.array(z.string())).optional()


#: Broadcast strategy kind.
BroadcastStrategy = Literal["parallel", "sequential"]


__all__ = [
    "AgentsSchema",
    "BindingsSchema",
    "BroadcastSchema",
    "BroadcastStrategy",
]
