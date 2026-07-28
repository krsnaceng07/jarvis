"""Zalo User runtime singleton."""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ZaloUserRuntime:
    started: bool = False
    last_message_at_ms: int = 0
    target_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


_RUNTIME_LOCK = threading.Lock()
_RUNTIME: ZaloUserRuntime | None = None


def set_zalouser_runtime(runtime: ZaloUserRuntime) -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = runtime


def get_zalouser_runtime() -> ZaloUserRuntime | None:
    with _RUNTIME_LOCK:
        return _RUNTIME


def reset_zalouser_runtime() -> None:
    global _RUNTIME
    with _RUNTIME_LOCK:
        _RUNTIME = None
