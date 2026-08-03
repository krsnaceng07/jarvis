"""jarvis.types.node_runtime_globals — type stub for Node.js runtime globals.

OpenClaw parity: mirrors
``openclaw-main/src/types/node-runtime-globals.d.ts``.

Phase 8.1b — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


#: Placeholder type alias for ``process.env`` lookup keys.
ProcessEnvKey = str

#: Placeholder type alias for ``Buffer`` byte values.
BufferBytes = bytes

#: Placeholder type alias for ``AbortSignal`` (Python 3.13+ has no built-in, see ``asyncio``).
AbortSignalLike = Any

#: Placeholder type alias for ``NodeJS.ProcessEnv`` (read-only env map).
NodeProcessEnv = Any

#: Placeholder type alias for ``NodeJS.Timeout`` returned by setTimeout.
NodeTimeout = Any


__all__ = [
    "ProcessEnvKey",
    "BufferBytes",
    "AbortSignalLike",
    "NodeProcessEnv",
    "NodeTimeout",
]
