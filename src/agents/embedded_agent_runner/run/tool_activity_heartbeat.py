"""jarvis.agents.embedded_agent_runner.run.tool_activity_heartbeat — track tool activity for the heartbeat.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/tool-activity-heartbeat.ts``.

Public surface:

Functions:

- :func:`clear_tool_activity_run`
- :func:`get_last_tool_activity_ms`
- :func:`notify_tool_activity`
- :func:`on_tool_activity`
- :func:`wrap_embedded_attempt_tool_with_activity`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional


#: Per-run tool-activity timestamps.
_TOOL_ACTIVITY_RUN: Dict[str, int] = {}


# ---------------------------------------------------------------------------
# Helpers (ported as-is)
# ---------------------------------------------------------------------------


def _now_ms() -> int:
    return int(time.time() * 1000)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def clear_tool_activity_run(run_id: Optional[str]) -> None:
    """Clear the tool-activity timestamp for a run.

    Mirrors :func:`clearToolActivityRun` (``tool-activity-heartbeat.ts``).
    """
    if not run_id:
        return
    _TOOL_ACTIVITY_RUN.pop(run_id, None)


def get_last_tool_activity_ms(run_id: Optional[str]) -> Optional[int]:
    """Return the last tool-activity timestamp for a run.

    Mirrors :func:`getLastToolActivityMs` (``tool-activity-heartbeat.ts``).
    """
    if not run_id:
        return None
    return _TOOL_ACTIVITY_RUN.get(run_id)


def notify_tool_activity(run_id: Optional[str]) -> None:
    """Notify that a tool became active for a run.

    Mirrors :func:`notifyToolActivity` (``tool-activity-heartbeat.ts``).
    """
    if not run_id:
        return
    _TOOL_ACTIVITY_RUN[run_id] = _now_ms()


def on_tool_activity(
    run_id: Optional[str],
    callback: Callable[[], None],
) -> None:
    """Register a callback to fire on every tool-activity update.

    Mirrors :func:`onToolActivity` (``tool-activity-heartbeat.ts``).
    """
    if not run_id or not callable(callback):
        return
    notify_tool_activity(run_id)
    try:
        callback()
    except Exception:
        pass


def wrap_embedded_attempt_tool_with_activity(
    tool: Any,
) -> Any:
    """Wrap an embedded-attempt tool with activity tracking.

    Mirrors :func:`wrapEmbeddedAttemptToolWithActivity`
    (``tool-activity-heartbeat.ts``).
    """
    if not isinstance(tool, dict):
        return tool

    run_id = tool.get("runId")
    tool_name = tool.get("name", "tool")

    def _activity_callback() -> None:
        on_tool_activity(run_id, lambda: None)

    return {
        **tool,
        "wrapped": True,
        "toolName": tool_name,
        "activityCallback": _activity_callback,
    }


__all__ = [
    "clear_tool_activity_run",
    "get_last_tool_activity_ms",
    "notify_tool_activity",
    "on_tool_activity",
    "wrap_embedded_attempt_tool_with_activity",
]
