"""Tests for assistant-message promotion and event lifecycles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jarvis_tool_call_repair import (
    PromotionOptions,
    create_promoted_plain_text_tool_call_block,
    create_promoted_plain_text_tool_call_events,
    project_standalone_plain_text_tool_call_message,
)
from jarvis_tool_call_repair.payload import PlainTextToolCallBlock


def _options(
    message: object,
    *,
    require_assistant_role: bool = False,
    allowed_stop_reasons: frozenset[str] | None = None,
    is_retainable_non_text_block: Callable[[dict[str, Any]], bool] | None = None,
) -> PromotionOptions:
    return PromotionOptions(
        allowed_tool_names=frozenset({"read"}),
        create_tool_call_block=create_promoted_plain_text_tool_call_block,
        message=message,
        require_assistant_role=require_assistant_role,
        allowed_stop_reasons=allowed_stop_reasons,
        is_retainable_non_text_block=is_retainable_non_text_block,
    )


def test_promote_string_content() -> None:
    projection = project_standalone_plain_text_tool_call_message(
        _options({"role": "assistant", "content": '[read]\n{"path": "/tmp"}[/read]'})
    )
    assert projection is not None
    content = projection.message["content"]
    assert isinstance(content, list) and len(content) == 1
    assert content[0]["type"] == "toolCall"
    assert content[0]["name"] == "read"
    assert projection.message["stopReason"] == "toolUse"


def test_promote_declines_unknown_names() -> None:
    projection = project_standalone_plain_text_tool_call_message(
        _options({"role": "assistant", "content": '[evil]\n{"x": 1}[/evil]'})
    )
    assert projection is None


def test_promote_requires_assistant_role_when_asked() -> None:
    message = {"role": "user", "content": '[read]\n{"x": 1}[/read]'}
    assert (
        project_standalone_plain_text_tool_call_message(
            _options(message, require_assistant_role=True)
        )
        is None
    )
    assert project_standalone_plain_text_tool_call_message(_options(message)) is not None


def test_promote_respects_stop_reasons() -> None:
    message = {
        "role": "assistant",
        "stopReason": "length",
        "content": '[read]\n{"x": 1}[/read]',
    }
    assert (
        project_standalone_plain_text_tool_call_message(
            _options(message, allowed_stop_reasons=frozenset({"stop"}))
        )
        is None
    )


def test_promote_mixed_content_with_retained_block() -> None:
    message = {
        "role": "assistant",
        "content": [
            {"type": "text", "text": '[read]\n{"x": 1}[/read]'},
            {"type": "image", "url": "https://example.com/i.png"},
        ],
    }
    projection = project_standalone_plain_text_tool_call_message(
        _options(
            message,
            is_retainable_non_text_block=lambda block: block.get("type") == "image",
        )
    )
    assert projection is not None
    assert [block["type"] for block in projection.message["content"]] == [
        "toolCall",
        "image",
    ]
    assert projection.source_to_projected_content_index == {1: 1}


def test_promote_declines_unresolvable_content() -> None:
    message = {"role": "assistant", "content": [{"type": "mystery"}]}
    assert project_standalone_plain_text_tool_call_message(_options(message)) is None
    assert project_standalone_plain_text_tool_call_message(_options({"role": "a"})) is None


def test_promoted_events_lifecycle() -> None:
    block = PlainTextToolCallBlock(name="read", arguments={"x": 1}, raw="r", start=0, end=1)
    tool_call = create_promoted_plain_text_tool_call_block(block, "read")
    assert tool_call["type"] == "toolCall"
    assert tool_call["id"].startswith("call_")
    assert tool_call["partialArgs"] == '{"x": 1}'
    message = {"content": [tool_call, {"type": "text", "text": "hi"}]}
    events = create_promoted_plain_text_tool_call_events(message)
    assert [event["type"] for event in events] == [
        "toolcall_start",
        "toolcall_delta",
        "toolcall_end",
    ]
    assert events[1]["delta"] == '{"x": 1}'
    assert events[2]["toolCall"] == tool_call


def test_promoted_tool_call_id_is_replay_stable() -> None:
    block = PlainTextToolCallBlock(name="read", arguments={"x": 1}, raw="r", start=3, end=4)
    first = create_promoted_plain_text_tool_call_block(block, "read")
    second = create_promoted_plain_text_tool_call_block(block, "read")
    assert first["id"] == second["id"]
