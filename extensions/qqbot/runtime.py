"""QQ Bot runtime singleton.

Mirrors the OpenClaw ``qqbot-runtime.ts`` pattern where
the channel holds a module-level runtime instance that the
host can set/inspect without going through the plugin API.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QQBotRuntime:
    """QQ Bot runtime state.

    Process-local singleton — only one active runtime per
    channel at a time. Thread-safe ``set/get``.
    """

    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: QQBotRuntime | None = None


def set_qqbot_runtime(runtime: QQBotRuntime) -> None:
    """Set the process-wide QQ Bot runtime instance."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_qqbot_runtime() -> QQBotRuntime | None:
    """Return the current QQ Bot runtime, or ``None``."""
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_qqbot_runtime() -> None:
    """Reset the runtime singleton (test helper)."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
