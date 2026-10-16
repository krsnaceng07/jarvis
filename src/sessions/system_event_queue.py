"""Backward-compatibility re-exports for jarvis_session_core.system_event_queue."""
from __future__ import annotations

from typing import Any

from jarvis_session_core.system_event_queue import (
    SystemEventQueue,
    dequeue_system_events,
    enqueue_system_event,
)
import jarvis_session_core.system_event_queue as _core_mod


def __getattr__(name: str) -> Any:
    return getattr(_core_mod, name)


__all__ = [
    "SystemEventQueue",
    "dequeue_system_events",
    "enqueue_system_event",
]
