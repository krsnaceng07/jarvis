"""Synology Chat runtime singleton."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SynologyChatRuntime:
    """Synology Chat runtime state."""

    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: SynologyChatRuntime | None = None


def set_synology_chat_runtime(runtime: SynologyChatRuntime) -> None:
    """Set the process-wide Synology Chat runtime instance."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_synology_chat_runtime() -> SynologyChatRuntime | None:
    """Return the current Synology Chat runtime, or ``None``."""
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_synology_chat_runtime() -> None:
    """Reset the runtime singleton (test helper)."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
