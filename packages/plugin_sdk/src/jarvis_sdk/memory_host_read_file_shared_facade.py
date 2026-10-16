"""jarvis_sdk.memory_host_read_file_shared_facade — public SDK re-export.

OpenClaw parity: mirrors
``packages/memory-host-sdk/src/memory-host-sdk/read-file-shared.ts``
(the SDK root facade that re-exports the public surface from
``host/read-file-shared.ts``).
"""

from __future__ import annotations

from .memory_host_read_file_shared import (
    DEFAULT_MEMORY_READ_LINES,
    DEFAULT_MEMORY_READ_MAX_CHARS,
    MemoryReadResult,
    build_memory_read_result,
    build_memory_read_result_from_slice,
)

__all__ = [
    "DEFAULT_MEMORY_READ_LINES",
    "DEFAULT_MEMORY_READ_MAX_CHARS",
    "MemoryReadResult",
    "build_memory_read_result",
    "build_memory_read_result_from_slice",
]
