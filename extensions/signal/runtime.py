"""Signal runtime singleton."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SignalRuntime:
    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: SignalRuntime | None = None


def set_signal_runtime(runtime: SignalRuntime) -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_signal_runtime() -> SignalRuntime | None:
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_signal_runtime() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
