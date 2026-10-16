from __future__ import annotations

import asyncio

from jarvis_sdk.tool_plugin import format_tool_result


def test_format_tool_result_matches_provider_result_shapes() -> None:
    assert format_tool_result("hello") == {
        "content": [{"type": "text", "text": "hello"}],
        "details": "hello",
    }
    assert format_tool_result({"value": 1}) == {
        "content": [{"type": "text", "text": '{\n  "value": 1\n}'}],
        "details": {"value": 1},
    }


def test_tool_wrapper_awaits_awaitable_returned_by_sync_callable() -> None:
    async def value() -> str:
        return "done"

    result = format_tool_result(asyncio.run(value()))
    assert result["details"] == "done"
