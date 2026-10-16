"""jarvis.agents.embedded_agent_runner.run.attempt_stop_reason_recovery — wrap a StreamFn to handle sensitive stop reasons.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.stop-reason-recovery.ts``.

Public surface:

- :func:`wrap_stream_fn_handle_sensitive_stop_reason`

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: StreamFn shape.
StreamFn = Any


#: Installable hook for the wrap-stream-fn step.
_WRAP_STREAM_FN_HANDLE_SENSITIVE_STOP_REASON: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_handle_sensitive_stop_reason_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnHandleSensitiveStopReason hook."""
    global _WRAP_STREAM_FN_HANDLE_SENSITIVE_STOP_REASON
    _WRAP_STREAM_FN_HANDLE_SENSITIVE_STOP_REASON = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_stream_fn_handle_sensitive_stop_reason(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a ``StreamFn`` to handle sensitive stop reasons.

    Mirrors :func:`wrapStreamFnHandleSensitiveStopReason`
    (``attempt.stop-reason-recovery.ts``).
    """
    return _WRAP_STREAM_FN_HANDLE_SENSITIVE_STOP_REASON({"baseFn": base_fn})


__all__ = [
    "StreamFn",
    "set_wrap_stream_fn_handle_sensitive_stop_reason_hook",
    "wrap_stream_fn_handle_sensitive_stop_reason",
]
