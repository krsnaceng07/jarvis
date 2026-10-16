"""jarvis.agents.embedded_agent_runner.run.attempt_model_diagnostic_events — wrap a StreamFn with diagnostic model-call events.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.model-diagnostic-events.ts``.

Public surface:

- :func:`wrap_stream_fn_with_diagnostic_model_call_events`

Phase 7.6f-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: StreamFn shape.
StreamFn = Any


#: Installable hook for the wrap-stream-fn-with-diagnostic-model-call-events step.
_WRAP_STREAM_FN_WITH_DIAGNOSTIC_MODEL_CALL_EVENTS: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_with_diagnostic_model_call_events_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnWithDiagnosticModelCallEvents hook."""
    global _WRAP_STREAM_FN_WITH_DIAGNOSTIC_MODEL_CALL_EVENTS
    _WRAP_STREAM_FN_WITH_DIAGNOSTIC_MODEL_CALL_EVENTS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_stream_fn_with_diagnostic_model_call_events(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn with diagnostic model-call events.

    Mirrors :func:`wrapStreamFnWithDiagnosticModelCallEvents`
    (``attempt.model-diagnostic-events.ts``).
    """
    return _WRAP_STREAM_FN_WITH_DIAGNOSTIC_MODEL_CALL_EVENTS(
        {"baseFn": base_fn}
    )


__all__ = [
    "StreamFn",
    "set_wrap_stream_fn_with_diagnostic_model_call_events_hook",
    "wrap_stream_fn_with_diagnostic_model_call_events",
]
