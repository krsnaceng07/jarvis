"""jarvis.memory — Memory runtime + storage helpers.

OpenClaw parity: mirrors ``src/memory/`` (root-memory-files.ts +
memory-runtime + memory-storage).

Re-export shim: a follow-up phase will physically move
``jarvis_sdk.memory_runtime`` and
``jarvis_sdk.memory_storage`` here and update all import
sites.
"""
from __future__ import annotations

from jarvis_sdk.memory_runtime import (  # noqa: F401
    resolve_memory_root_file,
    resolve_dreams_file_path,
    # Whatever else memory_runtime exports.
)
from jarvis_sdk.memory_storage import (  # noqa: F401
    MemoryStorage,
    open_memory_storage,
)
