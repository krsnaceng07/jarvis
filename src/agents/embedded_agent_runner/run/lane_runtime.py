"""jarvis.agents.embedded_agent_runner.run.lane_runtime — embedded-run lane runtime helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/lane-runtime.ts``.

Public surface:

Constants:

- :data:`EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS`
- :data:`EMBEDDED_RUN_LANE_HEARTBEAT_MS`

Functions:

- :func:`resolve_embedded_run_lane_timeout_ms`
- :func:`with_embedded_run_lane_timeout`
- :func:`resolve_embedded_run_session_queue_priority`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Default lane-timeout grace period (ms). Mirrors
#: :data:`EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS` (``lane-runtime.ts``).
EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS: int = 30_000


#: Default lane-heartbeat period (ms). Mirrors
#: :data:`EMBEDDED_RUN_LANE_HEARTBEAT_MS` (``lane-runtime.ts``).
EMBEDDED_RUN_LANE_HEARTBEAT_MS: int = EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS // 2


#: Installable hook for the resolve-embedded-run-lane-timeout-ms step.
_RESOLVE_EMBEDDED_RUN_LANE_TIMEOUT_MS: Callable[
    [int], int
] = lambda ms: int(ms) + EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS


def set_resolve_embedded_run_lane_timeout_ms_hook(
    hook: Callable[[int], int],
) -> None:
    """Install a custom resolveEmbeddedRunLaneTimeoutMs hook."""
    global _RESOLVE_EMBEDDED_RUN_LANE_TIMEOUT_MS
    _RESOLVE_EMBEDDED_RUN_LANE_TIMEOUT_MS = hook


#: Installable hook for the with-embedded-run-lane-timeout step.
_WITH_EMBEDDED_RUN_LANE_TIMEOUT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_with_embedded_run_lane_timeout_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom withEmbeddedRunLaneTimeout hook."""
    global _WITH_EMBEDDED_RUN_LANE_TIMEOUT
    _WITH_EMBEDDED_RUN_LANE_TIMEOUT = hook


#: Installable hook for the resolve-embedded-run-session-queue-priority step.
_RESOLVE_EMBEDDED_RUN_SESSION_QUEUE_PRIORITY: Callable[
    [Dict[str, Any]], int
] = lambda _p: 0


def set_resolve_embedded_run_session_queue_priority_hook(
    hook: Callable[[Dict[str, Any]], int],
) -> None:
    """Install a custom resolveEmbeddedRunSessionQueuePriority hook."""
    global _RESOLVE_EMBEDDED_RUN_SESSION_QUEUE_PRIORITY
    _RESOLVE_EMBEDDED_RUN_SESSION_QUEUE_PRIORITY = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_embedded_run_lane_timeout_ms(timeout_ms: int) -> int:
    """Resolve the embedded-run lane timeout in milliseconds.

    Mirrors :func:`resolveEmbeddedRunLaneTimeoutMs`
    (``lane-runtime.ts``).
    """
    return int(
        _RESOLVE_EMBEDDED_RUN_LANE_TIMEOUT_MS(int(timeout_ms or 0))
    )


def with_embedded_run_lane_timeout(params: Dict[str, Any]) -> Any:
    """Run an action with the embedded-run lane timeout.

    Mirrors :func:`withEmbeddedRunLaneTimeout`
    (``lane-runtime.ts``).
    """
    return _WITH_EMBEDDED_RUN_LANE_TIMEOUT(dict(params or {}))


def resolve_embedded_run_session_queue_priority(
    params: Dict[str, Any],
) -> int:
    """Resolve the embedded-run session queue priority.

    Mirrors :func:`resolveEmbeddedRunSessionQueuePriority`
    (``lane-runtime.ts``).
    """
    return int(
        _RESOLVE_EMBEDDED_RUN_SESSION_QUEUE_PRIORITY(dict(params or {}))
        or 0
    )


__all__ = [
    "EMBEDDED_RUN_LANE_HEARTBEAT_MS",
    "EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS",
    "resolve_embedded_run_lane_timeout_ms",
    "resolve_embedded_run_session_queue_priority",
    "set_resolve_embedded_run_lane_timeout_ms_hook",
    "set_resolve_embedded_run_session_queue_priority_hook",
    "set_with_embedded_run_lane_timeout_hook",
    "with_embedded_run_lane_timeout",
]
