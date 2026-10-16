"""Phase 7.5d tests — cli-backend-dispatch-transcript."""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from src.agents.embedded_agent_runner.cli_backend_dispatch_transcript import (
    create_cli_dispatch_transcript_recorder,
    set_append_transcript_message_hook,
    set_build_assistant_message_hook,
    set_build_usage_with_no_cost_hook,
)


def _install_default_hooks() -> None:
    set_append_transcript_message_hook(
        lambda _params: _default_append()
    )
    set_build_assistant_message_hook(lambda params: {"role": "assistant", **params})
    set_build_usage_with_no_cost_hook(lambda _p: {"input": 0, "output": 0})


async def _default_append() -> None:
    return None


# ============================================================================
# create_cli_dispatch_transcript_recorder
# ============================================================================


class TestCreateRecorder:
    def setup_method(self) -> None:
        _install_default_hooks()

    @pytest.mark.asyncio
    async def test_user_prompt_appended(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hello world",
                "provider": "anthropic",
            }
        )
        await recorder["finalize"]()
        # The user prompt + (no final text) = 1 message.
        assert len(appended) == 1
        msg = appended[0]["message"]
        assert msg["role"] == "user"
        assert msg["content"] == [{"type": "text", "text": "hello world"}]
        assert "timestamp" in msg

    @pytest.mark.asyncio
    async def test_tool_start_event(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteToolEvent"](
            {
                "phase": "start",
                "toolCallId": "t-1",
                "toolName": "bash",
                "args": {"command": "ls"},
            }
        )
        await recorder["finalize"]()
        # User prompt + tool call start = 2 messages.
        assert len(appended) == 2
        tool_msg = appended[1]["message"]
        assert tool_msg["role"] == "assistant"
        assert tool_msg["content"][0]["type"] == "toolCall"
        assert tool_msg["content"][0]["name"] == "bash"
        assert tool_msg["stopReason"] == "toolUse"

    @pytest.mark.asyncio
    async def test_tool_end_event(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteToolEvent"](
            {
                "phase": "end",
                "toolCallId": "t-1",
                "toolName": "bash",
                "result": "hello",
            }
        )
        await recorder["finalize"]()
        assert len(appended) == 2
        result_msg = appended[1]["message"]
        assert result_msg["role"] == "toolResult"
        assert result_msg["toolCallId"] == "t-1"
        assert result_msg["content"] == [{"type": "text", "text": "hello"}]

    @pytest.mark.asyncio
    async def test_tool_end_string_result_empty(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteToolEvent"](
            {
                "phase": "end",
                "toolCallId": "t-1",
                "toolName": "bash",
                "result": "",
            }
        )
        await recorder["finalize"]()
        # Empty string -> empty content.
        assert appended[1]["message"]["content"] == []

    @pytest.mark.asyncio
    async def test_tool_end_object_result(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteToolEvent"](
            {
                "phase": "end",
                "toolCallId": "t-1",
                "toolName": "bash",
                "result": {
                    "content": [
                        {"type": "text", "text": "ok"},
                        {"type": "image", "data": "x", "mimeType": "image/png"},
                    ],
                    "details": {"duration": 100},
                },
            }
        )
        await recorder["finalize"]()
        result_msg = appended[1]["message"]
        assert result_msg["content"] == [
            {"type": "text", "text": "ok"},
            {"type": "image", "data": "x", "mimeType": "image/png"},
        ]
        assert result_msg["details"] == {"duration": 100}
        assert result_msg["isError"] is False

    @pytest.mark.asyncio
    async def test_tool_end_is_error(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteToolEvent"](
            {
                "phase": "end",
                "toolCallId": "t-1",
                "toolName": "bash",
                "result": "fail",
                "isError": True,
            }
        )
        await recorder["finalize"]()
        assert appended[1]["message"]["isError"] is True

    @pytest.mark.asyncio
    async def test_note_assistant_text(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteAssistantText"]("hello world")
        await recorder["finalize"]("hello world")
        # User + final assistant = 2 messages.
        assert len(appended) == 2
        final = appended[1]["message"]
        assert final["role"] == "assistant"
        assert final["content"] == [{"type": "text", "text": "hello world"}]
        assert final["stopReason"] == "stop"

    @pytest.mark.asyncio
    async def test_note_assistant_text_ignores_blank(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteAssistantText"]("")
        recorder["noteAssistantText"]("   ")
        await recorder["finalize"]()
        # Only the user prompt.
        assert len(appended) == 1

    @pytest.mark.asyncio
    async def test_flush_assistant_snapshot(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteAssistantText"]("streaming text")
        recorder["flushAssistantSnapshot"]()
        recorder["flushAssistantSnapshot"]()  # dedup: same text -> no new message
        await recorder["finalize"]("streaming text")
        # User + flushed snapshot + (no final because same text).
        assert len(appended) == 2
        assert appended[1]["message"]["stopReason"] == "aborted"

    @pytest.mark.asyncio
    async def test_finalize_idempotent(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        await recorder["finalize"]("first")
        await recorder["finalize"]("second")  # idempotent
        # User + first finalize = 2 messages (second is a no-op).
        assert len(appended) == 2

    @pytest.mark.asyncio
    async def test_tool_event_after_finalize_no_op(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        await recorder["finalize"]("done")
        recorder["noteToolEvent"](
            {
                "phase": "start",
                "toolCallId": "t-1",
                "toolName": "bash",
                "args": {},
            }
        )
        # No new messages after finalize.
        assert len(appended) == 2

    @pytest.mark.asyncio
    async def test_tool_call_id_auto_generated(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
            }
        )
        recorder["noteToolEvent"](
            {
                "phase": "start",
                "toolName": "bash",
                "args": {},
            }
        )
        await recorder["finalize"]()
        # No toolCallId supplied -> auto-generated.
        tool_call_id = appended[1]["message"]["content"][0]["id"]
        assert tool_call_id == "run-1-tool-1"

    @pytest.mark.asyncio
    async def test_model_provider_id(self) -> None:
        appended: List[Dict[str, Any]] = []

        async def append(params: Dict[str, Any]) -> None:
            appended.append(params)

        set_append_transcript_message_hook(append)
        recorder = create_cli_dispatch_transcript_recorder(
            {
                "sessionId": "sess-1",
                "runId": "run-1",
                "prompt": "hi",
                "provider": "anthropic",
                "model": "claude-opus-4-6",
            }
        )
        recorder["noteAssistantText"]("ok")
        await recorder["finalize"]("ok")
        # The assistant message should reference the model.
        assert "model" in appended[1]["message"]
        assert appended[1]["message"]["model"]["api"] == "cli"
