"""jarvis_sdk.memory_host_hash — SHA-256 hashing for memory host.

OpenClaw parity: mirrors ``packages/memory-host-sdk/src/host/hash.ts`` (7 LOC).
Single helper: ``hash_text(value)`` returns the SHA-256 hex digest of
a UTF-8 string. Used for stable cache + content keys in the
memory host pipeline.
"""
from __future__ import annotations

import hashlib


def hash_text(value: str) -> str:
    """SHA-256 hex digest of ``value`` (UTF-8).

    Mirrors OpenClaw's ``hashText``. Returns 64 lowercase hex chars.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["hash_text"]
