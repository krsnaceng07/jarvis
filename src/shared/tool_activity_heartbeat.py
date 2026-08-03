"""jarvis.shared.tool_activity_heartbeat — per-run tool activity registry.

OpenClaw parity: mirrors ``openclaw-main/src/shared/tool-activity-heartbeat.ts``.
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Set

#: Per-run activity listeners.
_RUN_LISTENERS: Dict[str, Set[Callable[[], None]]] = {}
#: Per-run last-activity timestamps (epoch ms).
_RUN_LAST_ACTIVITY_MS: Dict[str, int] = {}


def notify_tool_activity(run_id: str) -> None:
    """Record ``run_id`` activity and notify listeners.

    Mirrors :func:`notifyToolActivity` (``shared/tool-activity-heartbeat.ts``).
    """
    if not isinstance(run_id, str) or not run_id:
        return
    _RUN_LAST_ACTIVITY_MS[run_id] = int(time.time() * 1000)
    listeners = _RUN_LISTENERS.get(run_id)
    if not listeners:
        return
    for listener in list(listeners):
        try:
            listener()
        except Exception:  # noqa: BLE001 — broadcast handler
            pass


def on_tool_activity(run_id: str, listener: Callable[[], None]) -> Callable[[], None]:
    """Register a listener for ``run_id`` activity and return an unsubscribe.

    Mirrors :func:`onToolActivity` (``shared/tool-activity-heartbeat.ts``).
    """
    listeners = _RUN_LISTENERS.get(run_id)
    if listeners is None:
        listeners = set()
        _RUN_LISTENERS[run_id] = listeners
    listeners.add(listener)

    def _unsubscribe() -> None:
        ls = _RUN_LISTENERS.get(run_id)
        if ls is None:
            return
        ls.discard(listener)
        if len(ls) == 0:
            _RUN_LISTENERS.pop(run_id, None)

    return _unsubscribe


def get_last_tool_activity_ms(run_id: str) -> int:
    """Return the last activity epoch-ms for ``run_id`` (0 if never seen).

    Mirrors :func:`getLastToolActivityMs` (``shared/tool-activity-heartbeat.ts``).
    """
    return _RUN_LAST_ACTIVITY_MS.get(run_id, 0)


def clear_tool_activity_run(run_id: str) -> None:
    """Drop all listeners and last-activity state for ``run_id``.

    Mirrors :func:`clearToolActivityRun` (``shared/tool-activity-heartbeat.ts``).
    """
    _RUN_LISTENERS.pop(run_id, None)
    _RUN_LAST_ACTIVITY_MS.pop(run_id, None)


__all__ = [
    "notify_tool_activity",
    "on_tool_activity",
    "get_last_tool_activity_ms",
    "clear_tool_activity_run",
]
