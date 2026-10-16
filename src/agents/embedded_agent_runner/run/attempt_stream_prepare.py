"""jarvis.agents.embedded_agent_runner.run.attempt_stream_prepare — prepare the stream for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt-stream-prepare.ts``.

Public surface:

- :func:`prepare_embedded_attempt_stream`

Phase 7.6d-5 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Embedded-attempt stream shape.
EmbeddedAttemptStream = Dict[str, Any]


#: Installable hook for the stream-prepare step.
_PREPARE_STREAM: Callable[[Dict[str, Any]], Any] = lambda _p: {}


def set_prepare_stream_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prepare-stream hook."""
    global _PREPARE_STREAM
    _PREPARE_STREAM = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prepare_embedded_attempt_stream(
    input_obj: Dict[str, Any],
) -> EmbeddedAttemptStream:
    """Prepare the stream for an attempt.

    Mirrors :func:`prepareEmbeddedAttemptStream`
    (``attempt-stream-prepare.ts``).
    """
    prepared = _PREPARE_STREAM(dict(input_obj or {}))
    if not isinstance(prepared, dict):
        prepared = {}
    return {
        "stream": prepared.get("stream") or {},
        "subscription": prepared.get("subscription"),
        "queueHandle": prepared.get("queueHandle"),
        "streamStrategy": prepared.get("streamStrategy"),
    }


__all__ = [
    "EmbeddedAttemptStream",
    "prepare_embedded_attempt_stream",
    "set_prepare_stream_hook",
]
