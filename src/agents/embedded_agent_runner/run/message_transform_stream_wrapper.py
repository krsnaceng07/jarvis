"""jarvis.agents.embedded_agent_runner.run.message_transform_stream_wrapper — wrap a StreamFn to transform message streams.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/message-transform-stream-wrapper.ts``.

Public surface:

- :func:`wrap_stream_fn_transform_messages`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: StreamFn shape.
StreamFn = Any


#: Installable hook for the wrap-stream-fn-transform-messages step.
_WRAP_STREAM_FN_TRANSFORM_MESSAGES: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_transform_messages_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnTransformMessages hook."""
    global _WRAP_STREAM_FN_TRANSFORM_MESSAGES
    _WRAP_STREAM_FN_TRANSFORM_MESSAGES = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_stream_fn_transform_messages(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn to transform message streams.

    Mirrors :func:`wrapStreamFnTransformMessages`
    (``message-transform-stream-wrapper.ts``).
    """
    return _WRAP_STREAM_FN_TRANSFORM_MESSAGES({"baseFn": base_fn})


__all__ = [
    "StreamFn",
    "set_wrap_stream_fn_transform_messages_hook",
    "wrap_stream_fn_transform_messages",
]
