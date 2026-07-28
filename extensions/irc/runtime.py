"""IRC runtime singleton.

Mirrors the OpenClaw ``irc-runtime.ts`` pattern where
the channel holds a module-level runtime instance that the
host can set/inspect without going through the plugin API.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IRCRuntime:
    """IRC runtime state.

    Process-local singleton — only one active runtime per
    channel at a time. Thread-safe ``set/get``.
    """

    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: IRCRuntime | None = None


def set_irc_runtime(runtime: IRCRuntime) -> None:
    """Set the process-wide IRC runtime instance."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_irc_runtime() -> IRCRuntime | None:
    """Return the current IRC runtime, or ``None``."""
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_irc_runtime() -> None:
    """Reset the runtime singleton (test helper)."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
