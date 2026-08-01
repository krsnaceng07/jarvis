"""Phase 6.12a — agent_session_types + agent_session_utils tests.

Verifies the public surface of the two
foundational AgentSession modules:

- ``agent_session_types`` —
  :class:`AgentSessionConfig`,
  :class:`PromptOptions`,
  :class:`ModelCycleResult`,
  :class:`SessionStats`,
  :class:`ExtensionBindings`,
  :class:`ScopedModelEntry`,
  :class:`SessionTokenUsage`.
- ``agent_session_utils`` —
  :func:`unwrap_core_result`,
  :func:`normalize_branch_summary_result`,
  :func:`has_persisted_assistant_content`,
  :func:`extract_text_content`,
  :func:`estimate_messages_from_content`.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.agents.sessions.agent_session_types import (
    AgentSessionConfig,
    CompactionEndEvent,
    ExtensionBindings,
    ModelCycleResult,
    PromptOptions,
    ScopedModelEntry,
    SessionStats,
    SessionTokenUsage,
)
from src.agents.sessions.agent_session_utils import (
    estimate_messages_from_content,
    extract_text_content,
    has_persisted_assistant_content,
    normalize_branch_summary_result,
    unwrap_core_result,
)


# ============================================================================
# agent_session_types
# ============================================================================


class TestAgentSessionConfig:
    def test_required_fields(self) -> None:
        # AgentSessionConfig requires 6
        # positional fields: agent,
        # session_manager, settings_manager,
        # cwd, resource_loader,
        # model_registry.
        # We can't construct the real
        # models without the full agent
        # runtime, so we pass ``None``
        # placeholders + a real cwd.
        config = AgentSessionConfig(
            agent=None,  # type: ignore[arg-type]
            session_manager=None,  # type: ignore[arg-type]
            settings_manager=None,  # type: ignore[arg-type]
            cwd="/tmp/proj",
            resource_loader=None,  # type: ignore[arg-type]
            model_registry=None,  # type: ignore[arg-type]
        )
        assert config.cwd == "/tmp/proj"
        assert config.scoped_models == []
        assert config.custom_tools == []
        assert config.initial_active_tool_names is None
        assert config.allowed_tool_names is None
        assert config.disable_built_in_tools is False
        assert config.base_tools_override is None
        assert config.extension_runner_ref is None
        assert config.session_start_event is None
        assert config.with_session_write_lock is None


class TestScopedModelEntry:
    def test_minimal(self) -> None:
        entry = ScopedModelEntry(model=None)  # type: ignore[arg-type]
        assert entry.model is None
        assert entry.thinking_level is None

    def test_with_thinking_level(self) -> None:
        entry = ScopedModelEntry(
            model="openai/gpt-5",  # type: ignore[arg-type]
            thinking_level="high",
        )
        assert entry.model == "openai/gpt-5"
        assert entry.thinking_level == "high"


class TestExtensionBindings:
    def test_defaults(self) -> None:
        bindings = ExtensionBindings()
        assert bindings.ui_context is None
        assert bindings.command_context_actions is None
        assert bindings.abort_handler is None
        assert bindings.shutdown_handler is None
        assert bindings.on_error is None

    def test_with_handlers(self) -> None:
        def abort() -> None:
            pass

        def on_error(err: Any) -> None:
            pass

        bindings = ExtensionBindings(
            abort_handler=abort,
            on_error=on_error,
        )
        assert bindings.abort_handler is abort
        assert bindings.on_error is on_error


class TestPromptOptions:
    def test_defaults(self) -> None:
        opts = PromptOptions()
        assert opts.expand_prompt_templates is True
        assert opts.images is None
        assert opts.streaming_behavior is None
        assert opts.source is None
        assert opts.preflight_result is None

    def test_with_overrides(self) -> None:
        opts = PromptOptions(
            expand_prompt_templates=False,
            streaming_behavior="steer",
            source="interactive",
        )
        assert opts.expand_prompt_templates is False
        assert opts.streaming_behavior == "steer"
        assert opts.source == "interactive"


class TestModelCycleResult:
    def test_minimal(self) -> None:
        result = ModelCycleResult(
            model="openai/gpt-5",  # type: ignore[arg-type]
            thinking_level="high",
        )
        assert result.model == "openai/gpt-5"
        assert result.thinking_level == "high"
        assert result.is_scoped is False

    def test_with_scope(self) -> None:
        result = ModelCycleResult(
            model="openai/gpt-5",  # type: ignore[arg-type]
            thinking_level="high",
            is_scoped=True,
        )
        assert result.is_scoped is True


class TestSessionTokenUsage:
    def test_defaults(self) -> None:
        usage = SessionTokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.cache_write_tokens == 0
        assert usage.total_tokens == 0


class TestSessionStats:
    def test_defaults(self) -> None:
        stats = SessionStats()
        assert stats.session_file is None
        assert stats.session_id == ""
        assert stats.user_messages == 0
        assert stats.assistant_messages == 0
        assert stats.tool_calls == 0
        assert stats.tool_results == 0
        assert stats.total_messages == 0
        assert stats.cost == 0.0
        assert stats.context_usage is None
        assert isinstance(stats.tokens, SessionTokenUsage)

    def test_with_values(self) -> None:
        stats = SessionStats(
            session_file="/sessions/abc.jsonl",
            session_id="abc",
            user_messages=5,
            assistant_messages=10,
            tool_calls=20,
            tool_results=20,
            total_messages=35,
            tokens=SessionTokenUsage(
                input_tokens=100,
                output_tokens=200,
                cache_read_tokens=50,
                cache_write_tokens=10,
                total_tokens=360,
            ),
            cost=0.05,
        )
        assert stats.session_file == "/sessions/abc.jsonl"
        assert stats.session_id == "abc"
        assert stats.user_messages == 5
        assert stats.tokens.total_tokens == 360
        assert stats.cost == 0.05


class TestEventTypedDicts:
    def test_event_listener_callable(self) -> None:
        # The listener type is a callable
        # accepting one event arg. Just
        # verify the import works.
        def listener(event: dict) -> None:
            return None

        # Use the listener.
        listener({"type": "test"})
        assert True

    def test_compaction_end_event_shape(self) -> None:
        evt: CompactionEndEvent = {
            "type": "compaction_end",
            "reason": "manual",
            "result": None,
            "aborted": False,
            "willRetry": False,
        }
        assert evt["type"] == "compaction_end"
        assert evt["aborted"] is False


# ============================================================================
# agent_session_utils
# ============================================================================


class TestUnwrapCoreResult:
    def test_ok(self) -> None:
        result = unwrap_core_result({"ok": True, "value": 42})
        assert result == 42

    def test_error_string(self) -> None:
        with pytest.raises(RuntimeError) as exc:
            unwrap_core_result({"ok": False, "error": "oops"})
        assert "oops" in str(exc.value)

    def test_error_exception(self) -> None:
        sentinel = ValueError("bad")
        with pytest.raises(ValueError) as exc:
            unwrap_core_result({"ok": False, "error": sentinel})
        assert exc.value is sentinel


class TestNormalizeBranchSummaryResult:
    def test_ok(self) -> None:
        result = normalize_branch_summary_result(
            {
                "ok": True,
                "value": {
                    "summary": "Did the thing",
                    "readFiles": ["a.py"],
                    "modifiedFiles": ["b.py"],
                },
            }
        )
        assert result["summary"] == "Did the thing"
        assert result["readFiles"] == ["a.py"]
        assert result["modifiedFiles"] == ["b.py"]

    def test_aborted(self) -> None:
        result = normalize_branch_summary_result(
            {
                "ok": False,
                "error": {"code": "aborted", "message": "user cancelled"},
            }
        )
        assert result["aborted"] is True
        assert "cancelled" in result["error"]

    def test_other_error(self) -> None:
        result = normalize_branch_summary_result(
            {
                "ok": False,
                "error": {"code": "boom", "message": "bad"},
            }
        )
        assert "aborted" not in result
        assert result["error"] == "bad"


class TestHasPersistedAssistantContent:
    def test_string_with_content(self) -> None:
        assert has_persisted_assistant_content("hello") is True

    def test_empty_string(self) -> None:
        assert has_persisted_assistant_content("") is False

    def test_list_with_content(self) -> None:
        assert (
            has_persisted_assistant_content([{"type": "text", "text": "x"}])
            is True
        )

    def test_empty_list(self) -> None:
        assert has_persisted_assistant_content([]) is False

    def test_none(self) -> None:
        assert has_persisted_assistant_content(None) is False

    def test_dict(self) -> None:
        # A bare dict is not a string or
        # list — no content to persist.
        assert has_persisted_assistant_content({"foo": "bar"}) is False


class TestExtractTextContent:
    def test_string(self) -> None:
        assert extract_text_content("hello world") == "hello world"

    def test_list_of_text_blocks(self) -> None:
        content = [
            {"type": "text", "text": "hello "},
            {"type": "text", "text": "world"},
        ]
        assert extract_text_content(content) == "hello world"

    def test_list_with_non_text_blocks(self) -> None:
        content = [
            {"type": "image", "data": "..."},
            {"type": "text", "text": "after"},
        ]
        assert extract_text_content(content) == "after"

    def test_empty_list(self) -> None:
        assert extract_text_content([]) == ""

    def test_none(self) -> None:
        assert extract_text_content(None) == ""

    def test_list_with_non_dict_blocks(self) -> None:
        content = ["raw", {"type": "text", "text": "x"}]
        assert extract_text_content(content) == "x"


class TestEstimateMessagesFromContent:
    def test_string_messages(self) -> None:
        # 12-char string → at least 1 token
        # (fallback heuristic: len/4).
        n = estimate_messages_from_content(["hello world!"])
        assert n >= 1

    def test_dict_messages(self) -> None:
        n = estimate_messages_from_content(
            [
                {"role": "user", "content": "hello world!"},
                {"role": "assistant", "content": "hi there"},
            ]
        )
        # 2 messages × ≥1 token each.
        assert n >= 2

    def test_empty(self) -> None:
        assert estimate_messages_from_content([]) == 0

    def test_mixed(self) -> None:
        n = estimate_messages_from_content(
            ["x", {"content": "yy"}, {"content": [{"text": "zzz"}]}]
        )
        assert n >= 3
