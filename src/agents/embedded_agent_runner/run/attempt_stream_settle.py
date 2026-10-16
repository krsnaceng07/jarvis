"""jarvis.agents.embedded_agent_runner.run.attempt_stream_settle — settle the attempt stream after dispatch.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stream-settle.ts``.

Public surface:

- :func:`settle_embedded_attempt_stream` (async)

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt stream-settle shape.
EmbeddedAttemptStreamSettle = Dict[str, Any]


#: Installable hook for the settle-embedded-attempt-stream step.
_SETTLE_EMBEDDED_ATTEMPT_STREAM: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_settle_embedded_attempt_stream_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom settle-embedded-attempt-stream hook."""
    global _SETTLE_EMBEDDED_ATTEMPT_STREAM
    _SETTLE_EMBEDDED_ATTEMPT_STREAM = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def settle_embedded_attempt_stream(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptStreamSettle:
    """Settle the attempt stream after dispatch.

    Mirrors :func:`settleEmbeddedAttemptStream`
    (``attempt-stream-settle.ts``).
    """
    settled: Any = await _maybe_await(
        _SETTLE_EMBEDDED_ATTEMPT_STREAM(dict(input_obj or {}))
    )
    if not isinstance(settled, dict):
        settled = {}
    return {
        "stream": settled.get("stream"),
        "streamStrategy": settled.get("streamStrategy"),
        "ready": bool(settled.get("ready", True)),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptStreamSettle",
    "set_settle_embedded_attempt_stream_hook",
    "settle_embedded_attempt_stream",
]
