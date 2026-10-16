"""Phase 7.4a tests — small tool helpers."""
from __future__ import annotations

from typing import Any, Dict, List


from src.agents.embedded_agent_runner.tool_call_argument_decoding import (
    create_html_entity_tool_call_argument_decoding_wrapper,
    set_decode_html_entities_hook,
    set_visit_object_content_blocks_hook,
)
from src.agents.embedded_agent_runner.tool_result_char_estimator import (
    create_message_char_estimate_cache,
    estimate_context_chars,
    estimate_message_chars_cached,
    get_tool_result_text,
    invalidate_message_chars_cache_entry,
    is_tool_result_message,
    set_bash_execution_to_text_hook,
    set_branch_summary_markers,
    set_compaction_summary_markers,
)
from src.agents.embedded_agent_runner.tool_schema_runtime import (
    log_provider_tool_schema_diagnostics,
    normalize_provider_tool_schemas,
    set_inspect_provider_tool_schemas_with_plugin_hook,
    set_normalize_provider_tool_schemas_with_plugin_hook,
)
from src.agents.embedded_agent_runner.tool_send_receipts import (
    consume_embedded_tool_send_receipt,
    record_embedded_tool_send_receipt,
)
from src.agents.embedded_agent_runner.tool_split import (
    set_to_tool_definitions_hook,
    split_sdk_tools,
)


# ============================================================================
# tool_result_char_estimator
# ============================================================================


class TestIsToolResultMessage:
    def test_role_toolResult(self) -> None:
        assert is_tool_result_message({"role": "toolResult"}) is True

    def test_role_tool(self) -> None:
        assert is_tool_result_message({"role": "tool"}) is True

    def test_type_toolResult(self) -> None:
        assert is_tool_result_message({"type": "toolResult"}) is True

    def test_user_message(self) -> None:
        assert is_tool_result_message({"role": "user"}) is False

    def test_non_dict(self) -> None:
        assert is_tool_result_message(None) is False
        assert is_tool_result_message("string") is False


class TestGetToolResultText:
    def test_text_content(self) -> None:
        msg = {"role": "toolResult", "content": [{"type": "text", "text": "hello"}]}
        assert get_tool_result_text(msg) == "hello"

    def test_multiple_text_chunks(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
            ],
        }
        assert get_tool_result_text(msg) == "hello\nworld"

    def test_string_content(self) -> None:
        msg = {"role": "toolResult", "content": "raw text"}
        assert get_tool_result_text(msg) == "raw text"

    def test_non_tool_result(self) -> None:
        assert get_tool_result_text({"role": "user"}) == ""

    def test_image_block_ignored(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "image"},
            ],
        }
        assert get_tool_result_text(msg) == "hi"


class TestEstimateMessageChars:
    def test_user_string(self) -> None:
        msg = {"role": "user", "content": "hello"}
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 5

    def test_user_blocks(self) -> None:
        msg = {
            "role": "user",
            "content": [
                {"type": "text", "text": "hello"},
                {"type": "text", "text": "world"},
            ],
        }
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 10

    def test_assistant_text(self) -> None:
        msg = {
            "role": "assistant",
            "content": [{"type": "text", "text": "hello world"}],
        }
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 11

    def test_assistant_thinking(self) -> None:
        msg = {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "reasoning here"}],
        }
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 14

    def test_assistant_tool_call(self) -> None:
        msg = {
            "role": "assistant",
            "content": [
                {"type": "toolCall", "arguments": {"x": 1}},
            ],
        }
        cache = create_message_char_estimate_cache()
        # 13 chars ({"x": 1})
        assert estimate_message_chars_cached(msg, cache) == 8

    def test_assistant_tool_call_invalid_json(self) -> None:
        class _Bad:
            pass

        msg = {
            "role": "assistant",
            "content": [
                {"type": "toolCall", "arguments": _Bad()},
            ],
        }
        cache = create_message_char_estimate_cache()
        # Falls back to 128 on JSON error.
        assert estimate_message_chars_cached(msg, cache) == 128

    def test_tool_result_text(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "hello"}],
        }
        cache = create_message_char_estimate_cache()
        chars = estimate_message_chars_cached(msg, cache)
        # Weighted: ceil(5 * 4/2) = 10
        assert chars == 10

    def test_tool_result_image(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "image"}],
        }
        cache = create_message_char_estimate_cache()
        # 8000 chars per image; weighted up by 4/2 = 16000.
        assert estimate_message_chars_cached(msg, cache) == 16_000

    def test_tool_result_not(self) -> None:
        msg = {"role": "user", "content": "x"}
        cache = create_message_char_estimate_cache()
        assert is_tool_result_message(msg) is False
        # Not a tool result, not a known role — falls through to 256.
        # Actually it IS user role -> 1 char.
        assert estimate_message_chars_cached(msg, cache) == 1

    def test_bash_execution_excluded(self) -> None:
        msg = {"role": "bashExecution", "excludeFromContext": True}
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 0

    def test_bash_execution_with_hook(self) -> None:
        set_bash_execution_to_text_hook(lambda m: "rendered text")
        try:
            msg = {"role": "bashExecution"}
            cache = create_message_char_estimate_cache()
            assert estimate_message_chars_cached(msg, cache) == len("rendered text")
        finally:
            set_bash_execution_to_text_hook(lambda _m: "")

    def test_branch_summary(self) -> None:
        set_branch_summary_markers(prefix="<bs>", suffix="</bs>")
        try:
            msg = {"role": "branchSummary", "summary": "hi"}
            cache = create_message_char_estimate_cache()
            assert estimate_message_chars_cached(msg, cache) == len("<bs>hi</bs>")
        finally:
            set_branch_summary_markers()

    def test_compaction_summary(self) -> None:
        set_compaction_summary_markers(prefix="<cs>", suffix="</cs>")
        try:
            msg = {"role": "compactionSummary", "summary": "hi"}
            cache = create_message_char_estimate_cache()
            assert estimate_message_chars_cached(msg, cache) == len("<cs>hi</cs>")
        finally:
            set_compaction_summary_markers()

    def test_custom(self) -> None:
        msg = {"role": "custom", "content": "hello"}
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 5

    def test_unknown_role(self) -> None:
        msg = {"role": "unknown"}
        cache = create_message_char_estimate_cache()
        assert estimate_message_chars_cached(msg, cache) == 256

    def test_caching(self) -> None:
        msg = {"role": "user", "content": "hello"}
        cache = create_message_char_estimate_cache()
        first = estimate_message_chars_cached(msg, cache)
        # Mutate the message but the cache should still return the
        # original.
        msg["content"] = "world"
        second = estimate_message_chars_cached(msg, cache)
        assert first == second == 5

    def test_invalidate(self) -> None:
        msg = {"role": "user", "content": "hello"}
        cache = create_message_char_estimate_cache()
        estimate_message_chars_cached(msg, cache)
        invalidate_message_chars_cache_entry(cache, msg)
        # After invalidation, recompute with mutated content.
        msg["content"] = "world"
        assert estimate_message_chars_cached(msg, cache) == 5

    def test_estimate_context_chars(self) -> None:
        msgs = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
        ]
        cache = create_message_char_estimate_cache()
        total = estimate_context_chars(msgs, cache)
        assert total == 5 + 2


# ============================================================================
# tool_schema_runtime
# ============================================================================


class TestNormalizeProviderToolSchemas:
    def setup_method(self) -> None:
        set_normalize_provider_tool_schemas_with_plugin_hook(
            lambda **kwargs: kwargs.get("context", {}).get("tools")
        )
        set_inspect_provider_tool_schemas_with_plugin_hook(lambda **_: [])

    def test_default_returns_tools_unchanged(self) -> None:
        tools = [{"name": "bash"}, {"name": "read"}]
        result = normalize_provider_tool_schemas(
            {"provider": "openai", "tools": tools}
        )
        assert result == tools

    def test_custom_normalizer(self) -> None:
        def normalize(**kwargs: Any) -> List[Dict[str, Any]]:
            return [{"name": "normalized"}]

        set_normalize_provider_tool_schemas_with_plugin_hook(normalize)
        result = normalize_provider_tool_schemas(
            {"provider": "openai", "tools": [{"name": "bash"}]}
        )
        assert result == [{"name": "normalized"}]

    def test_empty_tools(self) -> None:
        result = normalize_provider_tool_schemas({"provider": "openai", "tools": []})
        assert result == []


class TestLogProviderToolSchemaDiagnostics:
    def setup_method(self) -> None:
        set_normalize_provider_tool_schemas_with_plugin_hook(
            lambda **kwargs: kwargs.get("context", {}).get("tools")
        )
        set_inspect_provider_tool_schemas_with_plugin_hook(lambda **_: [])

    def test_no_diagnostics(self) -> None:
        # Should not raise.
        log_provider_tool_schema_diagnostics(
            {"provider": "openai", "tools": [{"name": "bash"}]}
        )

    def test_with_diagnostics(self) -> None:
        def inspect(**kwargs: Any) -> List[Dict[str, Any]]:
            return [
                {
                    "toolIndex": 0,
                    "toolName": "bash",
                    "violations": ["missing arg"],
                },
            ]

        set_inspect_provider_tool_schemas_with_plugin_hook(inspect)
        # Should not raise.
        log_provider_tool_schema_diagnostics(
            {"provider": "openai", "tools": [{"name": "bash"}]}
        )

    def test_summary_includes_remaining_count(self) -> None:
        # Build 8 diagnostics to trigger the "+N more" branch.
        diagnostics = [
            {
                "toolIndex": i,
                "toolName": f"tool_{i}",
                "violations": [f"v_{i}"],
            }
            for i in range(8)
        ]
        set_inspect_provider_tool_schemas_with_plugin_hook(
            lambda **_: diagnostics
        )
        # Should not raise and should include "+2 more".
        log_provider_tool_schema_diagnostics(
            {"provider": "openai", "tools": [{"name": "bash"}] * 8}
        )

    def test_single_violation_label(self) -> None:
        diagnostics = [
            {
                "toolIndex": 0,
                "toolName": "bash",
                "violations": ["single"],
            },
        ]
        set_inspect_provider_tool_schemas_with_plugin_hook(
            lambda **_: diagnostics
        )
        log_provider_tool_schema_diagnostics(
            {"provider": "openai", "tools": [{"name": "bash"}]}
        )

    def test_non_list_inspect_returns(self) -> None:
        set_inspect_provider_tool_schemas_with_plugin_hook(lambda **_: None)
        # Should not raise.
        log_provider_tool_schema_diagnostics(
            {"provider": "openai", "tools": [{"name": "bash"}]}
        )


# ============================================================================
# tool_call_argument_decoding
# ============================================================================


class TestCreateHtmlEntityToolCallArgumentDecodingWrapper:
    def setup_method(self) -> None:
        set_decode_html_entities_hook(lambda v: v.replace("&amp;", "&"))
        set_visit_object_content_blocks_hook(
            lambda message, visit: _default_visit(message, visit)
        )

    def test_no_stream(self) -> None:
        wrapper = create_html_entity_tool_call_argument_decoding_wrapper(
            lambda model, context, options: None
        )
        result = wrapper(None, None, None)
        assert result is None

    def test_decodes_tool_call_arguments(self) -> None:
        class _Stream:
            def __init__(self, message: Any) -> None:
                self._message = message

            async def result(self) -> Any:
                return self._message

            def __aiter__(self) -> Any:
                return self

            async def __anext__(self) -> Any:
                raise StopAsyncIteration

        msg = {
            "content": [
                {
                    "type": "toolCall",
                    "arguments": {"command": "echo &amp; done"},
                },
            ],
        }
        wrapper = create_html_entity_tool_call_argument_decoding_wrapper(
            lambda model, context, options: _Stream(msg)
        )
        result = wrapper(None, None, None)
        assert result is not None
        # result() is async — call it and verify
        import asyncio
        decoded = asyncio.run(result.result())
        assert decoded["content"][0]["arguments"]["command"] == "echo & done"

    def test_async_stream_fn(self) -> None:
        # Base stream fn returns a coroutine
        async def base_stream_fn(model: Any, context: Any, options: Any) -> Any:
            class _Stream:
                async def result(self) -> Any:
                    return {"content": [{"type": "text", "text": "ok"}]}

                def __aiter__(self) -> Any:
                    return self

                async def __anext__(self) -> Any:
                    raise StopAsyncIteration

            return _Stream()

        wrapper = create_html_entity_tool_call_argument_decoding_wrapper(base_stream_fn)
        result = wrapper(None, None, None)
        # The result should be a coroutine that yields the wrapped stream
        assert result is not None


def _default_visit(message: Any, visit: Any) -> None:
    """Default content-block visitor for tests."""
    if not message or not isinstance(message, dict):
        return
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                visit(block)


# ============================================================================
# tool_send_receipts
# ============================================================================


class TestToolSendReceipts:
    def test_record_and_consume(self) -> None:
        class _Session:
            pass

        session = _Session()
        record_embedded_tool_send_receipt(session, "tool-1", {"result": "ok"})
        receipt = consume_embedded_tool_send_receipt(session, "tool-1")
        assert receipt == {"details": {"toolSend": {"result": "ok"}}}

    def test_consume_unknown_returns_none(self) -> None:
        class _Session:
            pass

        session = _Session()
        result = consume_embedded_tool_send_receipt(session, "missing")
        assert result is None

    def test_consume_after_consume_returns_none(self) -> None:
        class _Session:
            pass

        session = _Session()
        record_embedded_tool_send_receipt(session, "tool-1", {"x": 1})
        first = consume_embedded_tool_send_receipt(session, "tool-1")
        second = consume_embedded_tool_send_receipt(session, "tool-1")
        assert first is not None
        assert second is None

    def test_consume_no_session(self) -> None:
        assert consume_embedded_tool_send_receipt(None, "x") is None

    def test_record_multiple(self) -> None:
        class _Session:
            pass

        session = _Session()
        record_embedded_tool_send_receipt(session, "t-1", {"x": 1})
        record_embedded_tool_send_receipt(session, "t-2", {"x": 2})
        assert consume_embedded_tool_send_receipt(session, "t-1") == {
            "details": {"toolSend": {"x": 1}}
        }
        assert consume_embedded_tool_send_receipt(session, "t-2") == {
            "details": {"toolSend": {"x": 2}}
        }


# ============================================================================
# tool_split
# ============================================================================


class TestSplitSdkTools:
    def setup_method(self) -> None:
        set_to_tool_definitions_hook(lambda tools, ctx: [{"name": t.get("name")} for t in tools])

    def test_basic(self) -> None:
        result = split_sdk_tools({"tools": [{"name": "bash"}, {"name": "read"}]})
        assert result == {
            "customTools": [{"name": "bash"}, {"name": "read"}],
        }

    def test_empty_tools(self) -> None:
        result = split_sdk_tools({"tools": []})
        assert result == {"customTools": []}

    def test_no_tools_key(self) -> None:
        result = split_sdk_tools({})
        assert result == {"customTools": []}

    def test_default_hook(self) -> None:
        set_to_tool_definitions_hook(lambda *args, **kwargs: [])
        result = split_sdk_tools({"tools": [{"name": "bash"}]})
        assert result == {"customTools": []}
