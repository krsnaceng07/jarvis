"""jarvis.agents.embedded_agent_runner.run.attempt_stream_transport — prepare the transport for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stream-transport.ts``.

Public surface:

- :func:`prepare_embedded_attempt_transport` (async)

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Embedded-attempt transport shape.
EmbeddedAttemptTransport = Dict[str, Any]


#: Installable hook for the prepare-transport step.
_PREPARE_TRANSPORT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_prepare_transport_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom prepare-transport hook."""
    global _PREPARE_TRANSPORT
    _PREPARE_TRANSPORT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def prepare_embedded_attempt_transport(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptTransport:
    """Prepare the transport for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptTransport`
    (``attempt-stream-transport.ts``).
    """
    transport: Any = await _maybe_await(
        _PREPARE_TRANSPORT(dict(input_obj or {}))
    )
    if not isinstance(transport, dict):
        transport = {}
    return {
        "effectiveAgentTransport": transport.get("effectiveAgentTransport"),
        "effectiveExtraParams": transport.get("effectiveExtraParams") or {},
        "effectivePromptCacheRetention": transport.get(
            "effectivePromptCacheRetention"
        ),
        "streamStrategy": transport.get("streamStrategy"),
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "EmbeddedAttemptTransport",
    "prepare_embedded_attempt_transport",
    "set_prepare_transport_hook",
]
