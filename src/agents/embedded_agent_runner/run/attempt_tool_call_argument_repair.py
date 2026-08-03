"""jarvis.agents.embedded_agent_runner.run.attempt_tool_call_argument_repair — wrap StreamFn to repair tool-call arguments.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.tool-call-argument-repair.ts``.

Public surface:

Functions:

- :func:`wrap_stream_fn_repair_malformed_tool_call_arguments`
- :func:`should_repair_malformed_tool_call_arguments`
- :func:`wrap_stream_fn_decode_xai_tool_call_arguments`

Phase 7.6f-2 — focused minimal port.

The OpenClaw source is large (~23K) and tightly couples stream
wrapping for tool-call argument repair. The Python port keeps the
public surface and delegates the heavy work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: StreamFn shape.
StreamFn = Any


#: Installable hook for the wrap-stream-fn-repair-malformed-tool-call-arguments step.
_WRAP_STREAM_FN_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_repair_malformed_tool_call_arguments_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnRepairMalformedToolCallArguments hook."""
    global _WRAP_STREAM_FN_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS
    _WRAP_STREAM_FN_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS = hook


#: Installable hook for the should-repair-malformed-tool-call-arguments step.
_SHOULD_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_repair_malformed_tool_call_arguments_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldRepairMalformedToolCallArguments hook."""
    global _SHOULD_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS
    _SHOULD_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS = hook


#: Installable hook for the wrap-stream-fn-decode-xai-tool-call-arguments step.
_WRAP_STREAM_FN_DECODE_XAI_TOOL_CALL_ARGUMENTS: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_decode_xai_tool_call_arguments_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnDecodeXaiToolCallArguments hook."""
    global _WRAP_STREAM_FN_DECODE_XAI_TOOL_CALL_ARGUMENTS
    _WRAP_STREAM_FN_DECODE_XAI_TOOL_CALL_ARGUMENTS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_stream_fn_repair_malformed_tool_call_arguments(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn to repair malformed tool-call arguments.

    Mirrors :func:`wrapStreamFnRepairMalformedToolCallArguments`
    (``attempt.tool-call-argument-repair.ts``).
    """
    return _WRAP_STREAM_FN_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS(
        {"baseFn": base_fn}
    )


def should_repair_malformed_tool_call_arguments(
    params: Dict[str, Any],
) -> bool:
    """Return True when tool-call argument repair should run.

    Mirrors :func:`shouldRepairMalformedToolCallArguments`
    (``attempt.tool-call-argument-repair.ts``).
    """
    return _SHOULD_REPAIR_MALFORMED_TOOL_CALL_ARGUMENTS(dict(params or {}))


def wrap_stream_fn_decode_xai_tool_call_arguments(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn to decode xAI tool-call arguments.

    Mirrors :func:`wrapStreamFnDecodeXaiToolCallArguments`
    (``attempt.tool-call-argument-repair.ts``).
    """
    return _WRAP_STREAM_FN_DECODE_XAI_TOOL_CALL_ARGUMENTS(
        {"baseFn": base_fn}
    )


__all__ = [
    "StreamFn",
    "set_should_repair_malformed_tool_call_arguments_hook",
    "set_wrap_stream_fn_decode_xai_tool_call_arguments_hook",
    "set_wrap_stream_fn_repair_malformed_tool_call_arguments_hook",
    "should_repair_malformed_tool_call_arguments",
    "wrap_stream_fn_decode_xai_tool_call_arguments",
    "wrap_stream_fn_repair_malformed_tool_call_arguments",
]
