"""jarvis_sdk.memory_host_hash_facade — public hash facade (memory-host-sdk).

OpenClaw parity: mirrors the hash facade re-export in
``packages/memory-host-sdk/src/host/hash.ts`` (7 LOC). Re-exports
``hash_text`` from the implementation module.
"""

from __future__ import annotations

from .memory_host_hash import hash_text

__all__ = ["hash_text"]
