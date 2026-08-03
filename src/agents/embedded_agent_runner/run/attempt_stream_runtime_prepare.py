"""jarvis.agents.embedded_agent_runner.run.attempt_stream_runtime_prepare — prepare the stream runtime for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stream-runtime-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_stream_runtime` (async)

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Embedded-attempt stream-runtime shape.
EmbeddedAttemptStreamRuntime = Dict[str, Any]


#: Installable hook for the prepare-stream-runtime step.
_PREPARE_STREAM_RUNTIME: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_stream_runtime_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepare-stream-runtime hook."""
    global _PREPARE_STREAM_RUNTIME
    _PREPARE_STREAM_RUNTIME = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_stream_runtime(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptStreamRuntime:
    """Prepare the stream runtime for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptStreamRuntime`
    (``attempt-stream-runtime-prepare.ts``).
    """
    runtime: Any = await _maybe_await(
        _PREPARE_STREAM_RUNTIME(dict(input_obj or {}))
    )
    if not isinstance(runtime, dict):
        runtime = {}
    return {
        "stream": runtime.get("stream") or {},
        "timeout": runtime.get("timeout") or {},
        "history": runtime.get("history") or {},
        "isProbeSession": bool(runtime.get("isProbeSession", False)),
        "abortable": runtime.get("abortable"),
        "cache": runtime.get("cache") or {},
        "onBlockReplyFlush": runtime.get("onBlockReplyFlush"),
        "promptActiveSession": runtime.get("promptActiveSession"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptStreamRuntime",
    "prepare_embedded_attempt_stream_runtime",
    "set_prepare_stream_runtime_hook",
]
