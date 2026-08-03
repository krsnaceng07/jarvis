"""jarvis.agents.embedded_agent_runner.run.progress_controller — control the progress polling for the embedded run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/progress-controller.ts``.

Public surface:

Functions:

- :func:`should_poll_progress`
- :func:`record_progress_poll`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Per-run last-progress-poll timestamp.
_LAST_PROGRESS_POLL: Dict[str, int] = {}


#: Default progress-poll interval (ms). Mirrors the inline default
#: in ``progress-controller.ts``.
DEFAULT_PROGRESS_POLL_INTERVAL_MS: int = 5_000


#: Installable hook for the should-poll-progress step.
_SHOULD_POLL_PROGRESS: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_poll_progress_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldPollProgress hook."""
    global _SHOULD_POLL_PROGRESS
    _SHOULD_POLL_PROGRESS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def should_poll_progress(
    params: Dict[str, Any],
) -> bool:
    """Return True when the progress should be polled.

    Mirrors :func:`shouldPollProgress` (``progress-controller.ts``).
    """
    return _SHOULD_POLL_PROGRESS(dict(params or {}))


def record_progress_poll(run_id: Optional[str]) -> int:
    """Record a progress poll for a run.

    Mirrors :func:`recordProgressPoll` (``progress-controller.ts``).
    """
    if not run_id:
        return 0
    _LAST_PROGRESS_POLL[run_id] = int(time.time() * 1000)
    return _LAST_PROGRESS_POLL[run_id]


__all__ = [
    "DEFAULT_PROGRESS_POLL_INTERVAL_MS",
    "record_progress_poll",
    "set_should_poll_progress_hook",
    "should_poll_progress",
]
