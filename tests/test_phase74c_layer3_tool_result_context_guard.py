"""Phase 7.4c tests — tool-result-context-guard."""
from __future__ import annotations

from typing import Any, Dict, List


from src.agents.embedded_agent_runner.tool_result_context_guard import (
    get_transcript_prompt_text,
    install_context_engine_loop_hook,
    install_tool_result_context_guard,
    mark_transcript_prompt_text,
    project_transcript_prompt_messages,
    set_context_engine_loop_hook_handler,
    set_tool_result_context_guard_handler,
    strip_transcript_prompt_marker,
    strip_transcript_prompt_markers,
)


# ============================================================================
# mark_transcript_prompt_text / get_transcript_prompt_text
# ============================================================================


class TestMarkAndGet:
    def test_mark_dict(self) -> None:
        msg = {"role": "user", "content": "hi"}
        mark_transcript_prompt_text(msg, "transcript text")
        assert get_transcript_prompt_text(msg) == "transcript text"

    def test_mark_object(self) -> None:
        class _Msg:
            role = "user"
            content = "hi"

        msg = _Msg()
        mark_transcript_prompt_text(msg, "transcript text")
        assert get_transcript_prompt_text(msg) == "transcript text"

    def test_mark_none(self) -> None:
        # Should not raise.
        mark_transcript_prompt_text(None, "x")
        assert get_transcript_prompt_text(None) is None

    def test_get_unmarked(self) -> None:
        msg = {"role": "user", "content": "hi"}
        assert get_transcript_prompt_text(msg) is None

    def test_mark_replaces(self) -> None:
        msg = {"role": "user", "content": "hi"}
        mark_transcript_prompt_text(msg, "first")
        mark_transcript_prompt_text(msg, "second")
        assert get_transcript_prompt_text(msg) == "second"

    def test_get_non_string_marker(self) -> None:
        msg = {"role": "user", "content": "hi"}
        msg["__jarvis_transcript_prompt_text__"] = 42
        assert get_transcript_prompt_text(msg) is None


# ============================================================================
# strip_transcript_prompt_marker
# ============================================================================


class TestStripMarker:
    def test_strip_unmarked_returns_same(self) -> None:
        msg = {"role": "user", "content": "hi"}
        assert strip_transcript_prompt_marker(msg) is msg

    def test_strip_dict(self) -> None:
        msg = {"role": "user", "content": "hi"}
        mark_transcript_prompt_text(msg, "x")
        stripped = strip_transcript_prompt_marker(msg)
        assert stripped is not msg
        assert get_transcript_prompt_text(stripped) is None
        assert stripped["content"] == "hi"

    def test_strip_object(self) -> None:
        class _Msg:
            role = "user"
            content = "hi"

        msg = _Msg()
        mark_transcript_prompt_text(msg, "x")
        stripped = strip_transcript_prompt_marker(msg)
        assert stripped is not msg
        assert get_transcript_prompt_text(stripped) is None

    def test_strip_none(self) -> None:
        assert strip_transcript_prompt_marker(None) is None


# ============================================================================
# project_transcript_prompt_messages
# ============================================================================


class TestProjectMessages:
    def test_no_markers_returns_same(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        cache: Dict[int, Any] = {}
        result = project_transcript_prompt_messages(messages, cache)
        assert result is messages

    def test_string_content_restore(self) -> None:
        messages = [
            {"role": "user", "content": "live prompt"},
        ]
        mark_transcript_prompt_text(messages[0], "transcript prompt")
        cache: Dict[int, Any] = {}
        result = project_transcript_prompt_messages(messages, cache)
        assert result is not messages
        assert result[0]["content"] == "transcript prompt"
        # The marker should be removed from the projected message.
        assert get_transcript_prompt_text(result[0]) is None

    def test_array_content_restore(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": "live prompt"}],
            },
        ]
        mark_transcript_prompt_text(messages[0], "transcript prompt")
        cache: Dict[int, Any] = {}
        result = project_transcript_prompt_messages(messages, cache)
        assert result[0]["content"][0]["text"] == "transcript prompt"
        assert get_transcript_prompt_text(result[0]) is None

    def test_non_user_role_skipped(self) -> None:
        messages = [
            {"role": "assistant", "content": "live"},
        ]
        mark_transcript_prompt_text(messages[0], "transcript")
        cache: Dict[int, Any] = {}
        result = project_transcript_prompt_messages(messages, cache)
        # Non-user role: not restored.
        assert result is messages

    def test_array_content_non_text_blocks(self) -> None:
        messages = [
            {
                "role": "user",
                "content": [{"type": "image"}, {"type": "text", "text": "live"}],
            },
        ]
        mark_transcript_prompt_text(messages[0], "transcript")
        cache: Dict[int, Any] = {}
        result = project_transcript_prompt_messages(messages, cache)
        # Text block restored; image preserved.
        assert result[0]["content"][0] == {"type": "image"}
        assert result[0]["content"][1]["text"] == "transcript"

    def test_cache_reused(self) -> None:
        messages = [
            {"role": "user", "content": "live"},
        ]
        mark_transcript_prompt_text(messages[0], "transcript")
        cache: Dict[int, Any] = {}
        result1 = project_transcript_prompt_messages(messages, cache)
        result2 = project_transcript_prompt_messages(result1, cache)
        # Second call should return the same list (no change).
        assert result2 is result1

    def test_none_messages(self) -> None:
        cache: Dict[int, Any] = {}
        result = project_transcript_prompt_messages([None, None], cache)
        assert result == [None, None]


# ============================================================================
# strip_transcript_prompt_markers
# ============================================================================


class TestStripMarkers:
    def test_strip_all(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "user", "content": "there"},
        ]
        mark_transcript_prompt_text(messages[0], "x")
        mark_transcript_prompt_text(messages[1], "y")
        result = strip_transcript_prompt_markers(messages)
        assert get_transcript_prompt_text(result[0]) is None
        assert get_transcript_prompt_text(result[1]) is None

    def test_no_markers_returns_same(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        result = strip_transcript_prompt_markers(messages)
        assert result is messages

    def test_empty(self) -> None:
        assert strip_transcript_prompt_markers([]) == []


# ============================================================================
# install hooks
# ============================================================================


class TestInstallContextEngineLoopHook:
    def setup_method(self) -> None:
        set_context_engine_loop_hook_handler(None)

    def test_default_no_handler(self) -> None:
        dispose = install_context_engine_loop_hook({})
        # Should return a no-op.
        assert dispose() is None

    def test_custom_handler(self) -> None:
        called: List[Dict[str, Any]] = []

        def handler(params: Dict[str, Any]) -> Callable[[], None]:
            called.append(params)

            def dispose() -> None:
                called.append({"dispose": True})

            return dispose

        set_context_engine_loop_hook_handler(handler)
        try:
            params = {"agent": "agent-1", "sessionId": "sess-1"}
            dispose = install_context_engine_loop_hook(params)
            assert called == [params]
            dispose()
            assert called == [params, {"dispose": True}]
        finally:
            set_context_engine_loop_hook_handler(None)


class TestInstallToolResultContextGuard:
    def setup_method(self) -> None:
        set_tool_result_context_guard_handler(None)

    def test_default_no_handler(self) -> None:
        dispose = install_tool_result_context_guard({})
        assert dispose() is None

    def test_custom_handler(self) -> None:
        called: List[Dict[str, Any]] = []

        def handler(params: Dict[str, Any]) -> Callable[[], None]:
            called.append(params)

            def dispose() -> None:
                called.append({"dispose": True})

            return dispose

        set_tool_result_context_guard_handler(handler)
        try:
            params = {"agent": "agent-1", "contextWindowTokens": 128_000}
            dispose = install_tool_result_context_guard(params)
            assert called == [params]
            dispose()
            assert called == [params, {"dispose": True}]
        finally:
            set_tool_result_context_guard_handler(None)
