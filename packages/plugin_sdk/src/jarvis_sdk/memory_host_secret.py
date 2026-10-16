"""jarvis_sdk.memory_host_secret — public secret facade (memory-host-sdk).

OpenClaw parity: mirrors the secret facade re-export in
``packages/memory-host-sdk/src/secret.ts`` (5 LOC). Re-exports the
two public API functions from ``memory_host_secret_input``.
"""

from __future__ import annotations

from .memory_host_secret_input import (
    has_configured_memory_secret_input,
    resolve_memory_secret_input_string,
)

__all__ = [
    "has_configured_memory_secret_input",
    "resolve_memory_secret_input_string",
]
