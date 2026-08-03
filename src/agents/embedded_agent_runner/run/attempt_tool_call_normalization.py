"""jarvis.agents.embedded_agent_runner.run.attempt_tool_call_normalization — wrap StreamFn to normalize tool calls.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.tool-call-normalization.ts``.

Public surface:

Functions:

- :func:`wrap_stream_fn_promote_standalone_text_tool_calls`
- :func:`wrap_stream_fn_trim_tool_call_names`
- :func:`should_apply_replay_tool_call_id_sanitizer`
- :func:`sanitize_replay_tool_call_ids_for_stream`
- :func:`sanitize_openai_responses_replay_for_stream`
- :func:`wrap_stream_fn_sanitize_malformed_tool_calls`

Phase 7.6f-2 — focused minimal port.

The OpenClaw source is large (~39K) and tightly couples stream
wrapping for tool-call normalization. The Python port keeps the
public surface and delegates the heavy work to installable hooks.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: StreamFn shape.
StreamFn = Any


#: Agent message shape.
AgentMessage = Dict[str, Any]


#: Installable hook for the wrap-stream-fn-promote-standalone-text-tool-calls step.
_WRAP_STREAM_FN_PROMOTE_STANDALONE_TEXT_TOOL_CALLS: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_promote_standalone_text_tool_calls_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnPromoteStandaloneTextToolCalls hook."""
    global _WRAP_STREAM_FN_PROMOTE_STANDALONE_TEXT_TOOL_CALLS
    _WRAP_STREAM_FN_PROMOTE_STANDALONE_TEXT_TOOL_CALLS = hook


#: Installable hook for the wrap-stream-fn-trim-tool-call-names step.
_WRAP_STREAM_FN_TRIM_TOOL_CALL_NAMES: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_trim_tool_call_names_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnTrimToolCallNames hook."""
    global _WRAP_STREAM_FN_TRIM_TOOL_CALL_NAMES
    _WRAP_STREAM_FN_TRIM_TOOL_CALL_NAMES = hook


#: Installable hook for the should-apply-replay-tool-call-id-sanitizer step.
_SHOULD_APPLY_REPLAY_TOOL_CALL_ID_SANITIZER: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_apply_replay_tool_call_id_sanitizer_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldApplyReplayToolCallIdSanitizer hook."""
    global _SHOULD_APPLY_REPLAY_TOOL_CALL_ID_SANITIZER
    _SHOULD_APPLY_REPLAY_TOOL_CALL_ID_SANITIZER = hook


#: Installable hook for the sanitize-replay-tool-call-ids-for-stream step.
_SANITIZE_REPLAY_TOOL_CALL_IDS_FOR_STREAM: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_sanitize_replay_tool_call_ids_for_stream_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom sanitizeReplayToolCallIdsForStream hook."""
    global _SANITIZE_REPLAY_TOOL_CALL_IDS_FOR_STREAM
    _SANITIZE_REPLAY_TOOL_CALL_IDS_FOR_STREAM = hook


#: Installable hook for the sanitize-openai-responses-replay-for-stream step.
_SANITIZE_OPENAI_RESPONSES_REPLAY_FOR_STREAM: Callable[
    [List[Dict[str, Any]]], List[Dict[str, Any]]
] = lambda messages: list(messages or [])


def set_sanitize_openai_responses_replay_for_stream_hook(
    hook: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
) -> None:
    """Install a custom sanitizeOpenAIResponsesReplayForStream hook."""
    global _SANITIZE_OPENAI_RESPONSES_REPLAY_FOR_STREAM
    _SANITIZE_OPENAI_RESPONSES_REPLAY_FOR_STREAM = hook


#: Installable hook for the wrap-stream-fn-sanitize-malformed-tool-calls step.
_WRAP_STREAM_FN_SANITIZE_MALFORMED_TOOL_CALLS: Callable[
    [Dict[str, Any]], Any
] = lambda p: p.get("baseFn")


def set_wrap_stream_fn_sanitize_malformed_tool_calls_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom wrapStreamFnSanitizeMalformedToolCalls hook."""
    global _WRAP_STREAM_FN_SANITIZE_MALFORMED_TOOL_CALLS
    _WRAP_STREAM_FN_SANITIZE_MALFORMED_TOOL_CALLS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def wrap_stream_fn_promote_standalone_text_tool_calls(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn to promote standalone text tool calls.

    Mirrors :func:`wrapStreamFnPromoteStandaloneTextToolCalls`
    (``attempt.tool-call-normalization.ts``).
    """
    return _WRAP_STREAM_FN_PROMOTE_STANDALONE_TEXT_TOOL_CALLS(
        {"baseFn": base_fn}
    )


def wrap_stream_fn_trim_tool_call_names(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn to trim tool-call names.

    Mirrors :func:`wrapStreamFnTrimToolCallNames`
    (``attempt.tool-call-normalization.ts``).
    """
    return _WRAP_STREAM_FN_TRIM_TOOL_CALL_NAMES({"baseFn": base_fn})


def should_apply_replay_tool_call_id_sanitizer(
    params: Dict[str, Any],
) -> bool:
    """Return True when the replay tool-call id sanitizer should run.

    Mirrors :func:`shouldApplyReplayToolCallIdSanitizer`
    (``attempt.tool-call-normalization.ts``).
    """
    return _SHOULD_APPLY_REPLAY_TOOL_CALL_ID_SANITIZER(dict(params or {}))


def sanitize_replay_tool_call_ids_for_stream(
    params: Dict[str, Any],
) -> Any:
    """Sanitize the replay tool-call ids for the stream.

    Mirrors :func:`sanitizeReplayToolCallIdsForStream`
    (``attempt.tool-call-normalization.ts``).
    """
    return _SANITIZE_REPLAY_TOOL_CALL_IDS_FOR_STREAM(dict(params or {}))


def sanitize_openai_responses_replay_for_stream(
    messages: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Sanitize OpenAI-Responses replay messages for the stream.

    Mirrors :func:`sanitizeOpenAIResponsesReplayForStream`
    (``attempt.tool-call-normalization.ts``).
    """
    return _SANITIZE_OPENAI_RESPONSES_REPLAY_FOR_STREAM(messages or [])


def wrap_stream_fn_sanitize_malformed_tool_calls(
    base_fn: StreamFn,
) -> StreamFn:
    """Wrap a StreamFn to sanitize malformed tool calls.

    Mirrors :func:`wrapStreamFnSanitizeMalformedToolCalls`
    (``attempt.tool-call-normalization.ts``).
    """
    return _WRAP_STREAM_FN_SANITIZE_MALFORMED_TOOL_CALLS(
        {"baseFn": base_fn}
    )


__all__ = [
    "AgentMessage",
    "StreamFn",
    "sanitize_openai_responses_replay_for_stream",
    "sanitize_replay_tool_call_ids_for_stream",
    "set_sanitize_openai_responses_replay_for_stream_hook",
    "set_sanitize_replay_tool_call_ids_for_stream_hook",
    "set_should_apply_replay_tool_call_id_sanitizer_hook",
    "set_wrap_stream_fn_promote_standalone_text_tool_calls_hook",
    "set_wrap_stream_fn_sanitize_malformed_tool_calls_hook",
    "set_wrap_stream_fn_trim_tool_call_names_hook",
    "should_apply_replay_tool_call_id_sanitizer",
    "wrap_stream_fn_promote_standalone_text_tool_calls",
    "wrap_stream_fn_sanitize_malformed_tool_calls",
    "wrap_stream_fn_trim_tool_call_names",
]
