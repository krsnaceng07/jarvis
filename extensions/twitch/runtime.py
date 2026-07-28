"""Twitch runtime singleton.

Mirrors the OpenClaw ``twitch-runtime.ts`` pattern where
the channel holds a module-level runtime instance that the
host can set/inspect without going through the plugin API.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TwitchRuntime:
    """Twitch runtime state.

    Process-local singleton — only one active runtime per
    channel at a time. Thread-safe ``set/get``.
    """

    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: TwitchRuntime | None = None


def set_twitch_runtime(runtime: TwitchRuntime) -> None:
    """Set the process-wide Twitch runtime instance."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_twitch_runtime() -> TwitchRuntime | None:
    """Return the current Twitch runtime, or ``None``."""
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_twitch_runtime() -> None:
    """Reset the runtime singleton (test helper)."""
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
