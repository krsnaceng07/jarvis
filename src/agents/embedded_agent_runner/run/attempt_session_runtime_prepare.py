"""jarvis.agents.embedded_agent_runner.run.attempt_session_runtime_prepare — prepare the session runtime for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-session-runtime-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_session_runtime` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt session-runtime shape.
EmbeddedAttemptSessionRuntime = Dict[str, Any]


#: Installable hook for the prepare-session-runtime step.
_PREPARE_SESSION_RUNTIME: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_session_runtime_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepare-session-runtime hook."""
    global _PREPARE_SESSION_RUNTIME
    _PREPARE_SESSION_RUNTIME = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_session_runtime(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptSessionRuntime:
    """Prepare the session runtime for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptSessionRuntime`
    (``attempt-session-runtime-prepare.ts``).
    """
    runtime: Any = await _maybe_await(
        _PREPARE_SESSION_RUNTIME(dict(input_obj or {}))
    )
    if not isinstance(runtime, dict):
        runtime = {}
    return {
        "sessionRuntime": runtime.get("sessionRuntime") or {},
        "state": runtime.get("state") or {},
        "toolResultPromptProjectionState": runtime.get(
            "toolResultPromptProjectionState"
        ),
        "sessionPromptState": runtime.get("sessionPromptState"),
        "trajectoryRecorder": runtime.get("trajectoryRecorder"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptSessionRuntime",
    "prepare_embedded_attempt_session_runtime",
    "set_prepare_session_runtime_hook",
]
