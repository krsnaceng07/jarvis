"""jarvis.config.zod_schema_node_host — node-host Zod schema fragments.

OpenClaw parity: mirrors
``openclaw-main/src/config/zod-schema.node-host.ts``.
"""
from __future__ import annotations

from typing import Any


#: Browser snapshot defaults schema.
BrowserSnapshotDefaultsSchema: Any = None  # z.object({mode: "efficient"}).strict().optional()


#: Node-host agent runs schema.
NodeHostAgentRunsSchema: Any = None  # z.object({claude}).strict().optional()


__all__ = [
    "BrowserSnapshotDefaultsSchema",
    "NodeHostAgentRunsSchema",
]
