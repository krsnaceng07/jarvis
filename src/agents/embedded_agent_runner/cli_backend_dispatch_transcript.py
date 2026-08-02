"""jarvis.agents.embedded_agent_runner.cli_backend_dispatch_transcript — CLI dispatch transcript recorder.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/cli-backend-dispatch-transcript.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`CliDispatchTranscriptRecorder` — TypedDict for the
  recorder returned by :func:`create_cli_dispatch_transcript_recorder`.
- :func:`create_cli_dispatch_transcript_recorder` — build a
  recorder that enqueues transcript messages (user prompt +
  tool events + assistant snapshot + final text) on a best-
  effort async tail.

Phase 7.5d — focused minimal port.

The OpenClaw source uses :func:`appendTranscriptMessage` from
``session-runtime.js`` and the message-builder helpers from
``runtime/index.js``. The Python port keeps the public surface
and delegates the heavy message-append + message-build to
installable hooks so the host can plug in the real layers as
they land.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Recorder returned by :func:`create_cli_dispatch_transcript_recorder`.
#: Mirrors :class:`CliDispatchTranscriptRecorder``
#: (``cli-backend-dispatch-transcript.ts``).
CliDispatchTranscriptRecorder = Dict[str, Any]


#: Async message-append hook. The host installs the real
#: :func:`appendTranscriptMessage`` when the session-runtime
#: layer lands. The default is a no-op.
_APPEND_TRANSCRIPT_MESSAGE: Callable[
    [Dict[str, Any]], Awaitable[None]
] = (
    lambda _params: _default_append()
)


async def _default_append() -> None:
    return None


def set_append_transcript_message_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[None]],
) -> None:
    """Install a custom append-transcript-message hook."""
    global _APPEND_TRANSCRIPT_MESSAGE
    _APPEND_TRANSCRIPT_MESSAGE = hook


#: Build-assistant-message hook. The host installs the real
#: :func:`buildAssistantMessage`` when the runtime layer lands.
#: The default sets ``role="assistant"`` so the produced message
#: matches the runtime shape.
_BUILD_ASSISTANT_MESSAGE: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda params: {"role": "assistant", **params}
)


def set_build_assistant_message_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom build-assistant-message hook."""
    global _BUILD_ASSISTANT_MESSAGE
    _BUILD_ASSISTANT_MESSAGE = hook


#: Build-usage-with-no-cost hook. The host installs the real
#: :func:`buildUsageWithNoCost`` when the usage layer lands.
#: The default returns ``{"input": 0, "output": 0}``.
_BUILD_USAGE_WITH_NO_COST: Callable[[Dict[str, Any]], Dict[str, Any]] = (
    lambda _params: {"input": 0, "output": 0}
)


def set_build_usage_with_no_cost_hook(
    hook: Callable[[Dict[str, Any]], Dict[str, Any]],
) -> None:
    """Install a custom build-usage-with-no-cost hook."""
    global _BUILD_USAGE_WITH_NO_COST
    _BUILD_USAGE_WITH_NO_COST = hook


def _now_ms() -> int:
    return int(time.time() * 1000)


def _build_zero_usage_assistant_message(
    content: List[Dict[str, Any]],
    stop_reason: str,
    *,
    model: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a zero-usage assistant message via the host's hook.

    Mirrors :func:`buildZeroUsageAssistantMessage``
    (``cli-backend-dispatch-transcript.ts:105-108``).
    """
    return _BUILD_ASSISTANT_MESSAGE(
        {
            "model": model,
            "content": content,
            "stopReason": stop_reason,
            "usage": _BUILD_USAGE_WITH_NO_COST({}),
        }
    )


def _normalize_tool_result_content(result: Any) -> List[Dict[str, Any]]:
    """Map a sanitized CLI tool result onto transcript content blocks.

    Mirrors :func:`normalizeToolResultContent``
    (``cli-backend-dispatch-transcript.ts:183-219``).
    """
    if isinstance(result, str):
        return [{"type": "text", "text": result}] if result else []
    if not result or not isinstance(result, dict):
        return []
    content = result.get("content") if isinstance(result.get("content"), list) else (
        result if isinstance(result, list) else None
    )
    if not isinstance(content, list):
        return []
    blocks: List[Dict[str, Any]] = []
    for block in content:
        if isinstance(block, str):
            blocks.append({"type": "text", "text": block})
            continue
        if not block or not isinstance(block, dict):
            continue
        type_ = block.get("type")
        text = block.get("text")
        if type_ == "text" and isinstance(text, str):
            blocks.append({"type": "text", "text": text})
            continue
        data = block.get("data")
        mime_type = block.get("mimeType")
        if (
            type_ == "image"
            and isinstance(data, str)
            and isinstance(mime_type, str)
        ):
            blocks.append({"type": "image", "data": data, "mimeType": mime_type})
    return blocks


def _read_tool_result_details(result: Any) -> Any:
    """Return the ``details`` sub-object of a tool result, if any.

    Mirrors :func:`readToolResultDetails``
    (``cli-backend-dispatch-transcript.ts:221-227``).
    """
    if not result or not isinstance(result, dict):
        return None
    details = result.get("details")
    return details if details and isinstance(details, dict) else None


def _create_initial_tail() -> "asyncio.Future[None]":
    """Create the initial resolved tail future."""
    loop = asyncio.get_event_loop()
    if loop.is_running():
        future: "asyncio.Future[None]" = loop.create_future()
        future.set_result(None)
        return future
    future = asyncio.Future()
    future.set_result(None)
    return future


def create_cli_dispatch_transcript_recorder(
    params: Dict[str, Any],
) -> CliDispatchTranscriptRecorder:
    """Build a CLI dispatch transcript recorder.

    Mirrors :func:`createCliDispatchTranscriptRecorder``
    (``cli-backend-dispatch-transcript.ts:54-180``).
    """
    last_assistant_text = ""
    last_written_assistant_text = ""
    finalized = False
    tool_record_sequence = 0
    scope = {
        "sessionId": params.get("sessionId"),
        "sessionKey": params.get("sessionKey"),
        "agentId": params.get("agentId"),
        "sessionFile": params.get("sessionFile"),
    }
    model: Dict[str, Any] = {
        "api": "cli",
        "provider": params.get("provider", ""),
        "id": params.get("model") or "",
    }
    # `tail` is the latest in-flight future. New enqueues are
    # chained via `asyncio.ensure_future(tail).then(_run)`.
    tail: "asyncio.Future[None]" = _create_initial_tail()

    def _enqueue(builder: Callable[[], Dict[str, Any]]) -> None:
        nonlocal tail

        async def _run() -> None:
            await _APPEND_TRANSCRIPT_MESSAGE(
                {
                    "message": builder(),
                    "scope": scope,
                    "config": params.get("config"),
                    "cwd": params.get("cwd"),
                }
            )

        previous = tail

        async def _chained() -> None:
            try:
                await previous
                await _run()
            except Exception as err:
                _log_append_failure(params, err)

        new_tail: "asyncio.Future[None]" = asyncio.Future()

        def _on_done(_task: Any) -> None:
            if not new_tail.done():
                if _task.cancelled():
                    new_tail.cancel()
                else:
                    exc = _task.exception()
                    if exc is not None:
                        new_tail.set_exception(exc)
                    else:
                        new_tail.set_result(None)

        task = asyncio.ensure_future(_chained())
        task.add_done_callback(_on_done)
        tail = new_tail

    def _log_append_failure(p: Dict[str, Any], err: Any) -> None:
        from .logger import log

        log.warning(
            f"cli dispatch transcript append failed: runId={p.get('runId', '')} error={err}"
        )

    _enqueue(
        lambda: {
            "role": "user",
            "content": [{"type": "text", "text": params.get("prompt", "")}],
            "timestamp": _now_ms(),
        }
    )

    def _note_tool_event(event: Dict[str, Any]) -> None:
        nonlocal tool_record_sequence
        if finalized:
            return
        tool_record_sequence += 1
        tool_call_id = (
            (event.get("toolCallId") or "").strip()
            or f"{params.get('runId', '')}-tool-{tool_record_sequence}"
        )
        if event.get("phase") == "start":
            _enqueue(
                lambda: _build_zero_usage_assistant_message(
                    [
                        {
                            "type": "toolCall",
                            "id": tool_call_id,
                            "name": event.get("toolName"),
                            "arguments": event.get("args") or {},
                        },
                    ],
                    "toolUse",
                    model=model,
                )
            )
            return
        _enqueue(
            lambda: {
                "role": "toolResult",
                "toolCallId": tool_call_id,
                "toolName": event.get("toolName"),
                "content": _normalize_tool_result_content(event.get("result")),
                "details": _read_tool_result_details(event.get("result")),
                "isError": event.get("isError") is True,
                "timestamp": _now_ms(),
            }
        )

    def _note_assistant_text(text: str) -> None:
        nonlocal last_assistant_text
        if not finalized and text and text.strip():
            last_assistant_text = text

    def _flush_assistant_snapshot() -> None:
        nonlocal last_written_assistant_text
        if finalized:
            return
        text = last_assistant_text.strip()
        if not text or text == last_written_assistant_text:
            return
        last_written_assistant_text = text
        _enqueue(
            lambda: _build_zero_usage_assistant_message(
                [{"type": "text", "text": text}],
                "aborted",
                model=model,
            )
        )

    async def _finalize(final_text: Optional[str] = None) -> None:
        nonlocal finalized, last_written_assistant_text
        if finalized:
            await tail
            return
        finalized = True
        text = (final_text or last_assistant_text or "").strip()
        if text and text != last_written_assistant_text:
            last_written_assistant_text = text
            _enqueue(
                lambda: _build_zero_usage_assistant_message(
                    [{"type": "text", "text": text}],
                    "stop",
                    model=model,
                )
            )
        await tail

    return {
        "noteToolEvent": _note_tool_event,
        "noteAssistantText": _note_assistant_text,
        "flushAssistantSnapshot": _flush_assistant_snapshot,
        "finalize": _finalize,
    }


__all__ = [
    "CliDispatchTranscriptRecorder",
    "create_cli_dispatch_transcript_recorder",
    "set_append_transcript_message_hook",
    "set_build_assistant_message_hook",
    "set_build_usage_with_no_cost_hook",
]
