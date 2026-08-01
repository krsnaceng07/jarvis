"""Phase 6.12b — agent_session_base tests.

Verifies the foundational
:class:`AgentSessionBase` class:

- Constructor binds the agent + session
  manager + settings manager + model
  registry + extension runner ref.
- Mutable state attributes are
  initialised to the expected defaults
  (empty tool maps, no current extension
  runner, no queued messages, etc.).
- ``emit`` fans out to every listener.
- ``emit_queue_update`` emits a
  ``queue_update`` event with the
  current steering + follow-up message
  lists.
- ``subscribe`` returns an unsubscribe
  callable; calling the unsubscribe
  removes the listener.
- ``run_with_session_write_lock`` runs
  the task through the configured
  ``withSessionWriteLock`` (when set)
  or without a lock (when unset).
- ``get_required_request_auth`` raises
  when the model has no API key.
- ``get_compaction_request_auth``
  returns ``{}`` on missing key.

The :class:`AgentSessionConfig` is
constructed with placeholder values
(``None`` for the agent + session
manager + settings manager + model
registry) so the constructor can be
tested without a real Layer 1 /
Layer 2 stack.
"""
from __future__ import annotations

from typing import Any

import pytest

from src.agents.sessions.agent_session_base import (
    ActiveToolPromptMetadata,
    AgentSessionBase,
    BuildSystemPromptOptions,
    ToolDefinitionEntry,
)
from src.agents.sessions.agent_session_types import AgentSessionConfig


def _make_config(**overrides) -> AgentSessionConfig:
    """Build a minimal AgentSessionConfig
    for the base-class tests. The agent /
    session_manager / settings_manager /
    model_registry / resource_loader are
    all ``None`` placeholders — the tests
    that need them set the real value via
    ``overrides``."""
    defaults: dict = {
        "agent": None,  # type: ignore[arg-type]
        "session_manager": None,  # type: ignore[arg-type]
        "settings_manager": None,  # type: ignore[arg-type]
        "cwd": "/tmp/proj",
        "resource_loader": None,  # type: ignore[arg-type]
        "model_registry": None,  # type: ignore[arg-type]
    }
    defaults.update(overrides)
    return AgentSessionConfig(**defaults)


# ============================================================================
# Constructor + state
# ============================================================================


class TestConstructor:
    def test_required_fields(self) -> None:
        config = _make_config()
        session = AgentSessionBase(config)
        assert session.agent is None
        assert session.session_manager is None
        assert session.settings_manager is None
        assert session.cwd == "/tmp/proj"
        assert session.session_resource_loader is None
        assert session.session_model_registry is None

    def test_scoped_models(self) -> None:
        from src.agents.sessions.agent_session_types import ScopedModelEntry

        config = _make_config(
            scoped_models=[
                ScopedModelEntry(model="m1"),  # type: ignore[arg-type]
                ScopedModelEntry(
                    model="m2",  # type: ignore[arg-type]
                    thinking_level="high",
                ),
            ]
        )
        session = AgentSessionBase(config)
        assert len(session.scoped_model_entries) == 2
        assert session.scoped_model_entries[0]["model"] == "m1"
        assert session.scoped_model_entries[1]["thinkingLevel"] == "high"

    def test_custom_tools(self) -> None:
        config = _make_config(custom_tools=[{"name": "x"}])
        session = AgentSessionBase(config)
        assert session.custom_tools == [{"name": "x"}]

    def test_allowed_tool_names(self) -> None:
        config = _make_config(allowed_tool_names=["a", "b"])
        session = AgentSessionBase(config)
        assert session.allowed_tool_names == {"a", "b"}

    def test_disable_built_in_tools(self) -> None:
        config = _make_config(disable_built_in_tools=True)
        session = AgentSessionBase(config)
        assert session.disable_built_in_tools is True

    def test_session_start_event_default(self) -> None:
        config = _make_config()
        session = AgentSessionBase(config)
        assert session.session_start_event == {
            "type": "session_start",
            "reason": "startup",
        }

    def test_session_start_event_override(self) -> None:
        config = _make_config(
            session_start_event={
                "type": "session_start",
                "reason": "resume",
                "sessionId": "abc",
            }
        )
        session = AgentSessionBase(config)
        assert session.session_start_event["sessionId"] == "abc"


class TestInitialState:
    def test_default_state(self) -> None:
        session = AgentSessionBase(_make_config())
        # Tool maps.
        assert session.base_tool_definitions == {}
        assert session.tool_registry == {}
        assert session.tool_definitions == {}
        assert session.tool_prompt_snippets == {}
        assert session.tool_prompt_guidelines == {}
        # System prompt.
        assert session.base_system_prompt == ""
        assert isinstance(session.base_system_prompt_options, BuildSystemPromptOptions)
        assert session.exact_base_system_prompt is None
        assert session.system_prompt_override is None
        # Extension / turn.
        assert session.current_extension_runner is None
        assert session.turn_index == 0
        # Compaction.
        assert session.compaction_abort_controller is None
        assert session.auto_compaction_abort_controller is None
        assert session.overflow_recovery_attempted is False
        # Branch summarisation.
        assert session.branch_summary_abort_controller is None
        assert session.extension_modified_tool_result_ids == set()
        # Retry.
        assert session.retry_abort_controller is None
        assert session.retry_count == 0
        # Bash.
        assert session.bash_abort_controller is None
        assert session.pending_bash_messages == []
        # Event subscription.
        assert session.event_listeners == []
        assert session.unsubscribe_agent is None
        # Queues.
        assert session.steering_messages == []
        assert session.follow_up_messages == []
        assert session.pending_next_turn_messages == []
        # Last assistant.
        assert session.last_assistant_message is None
        assert session.last_run_ended_for_turn_handoff is False


# ============================================================================
# Event subscription
# ============================================================================


class TestEmit:
    def test_fans_out_to_all_listeners(self) -> None:
        session = AgentSessionBase(_make_config())
        seen: list = []
        session.subscribe(lambda evt: seen.append(evt))
        session.subscribe(lambda evt: seen.append(("b", evt)))
        session.emit({"type": "test"})
        assert len(seen) == 2
        assert seen[0] == {"type": "test"}
        assert seen[1] == ("b", {"type": "test"})

    def test_no_listeners(self) -> None:
        session = AgentSessionBase(_make_config())
        # Should not raise.
        session.emit({"type": "test"})


class TestEmitQueueUpdate:
    def test_emit_with_empty_queues(self) -> None:
        session = AgentSessionBase(_make_config())
        seen: list = []
        session.subscribe(lambda evt: seen.append(evt))
        session.emit_queue_update()
        assert seen == [
            {
                "type": "queue_update",
                "steering": [],
                "followUp": [],
            }
        ]

    def test_emit_with_messages(self) -> None:
        session = AgentSessionBase(_make_config())
        session.steering_messages = ["a", "b"]
        session.follow_up_messages = ["c"]
        seen: list = []
        session.subscribe(lambda evt: seen.append(evt))
        session.emit_queue_update()
        assert seen[0]["steering"] == ["a", "b"]
        assert seen[0]["followUp"] == ["c"]


class TestSubscribe:
    def test_unsubscribe(self) -> None:
        session = AgentSessionBase(_make_config())
        seen: list = []

        def listener(evt: Any) -> None:
            seen.append(evt)

        unsubscribe = session.subscribe(listener)
        session.emit({"type": "a"})
        unsubscribe()
        session.emit({"type": "b"})
        assert seen == [{"type": "a"}]

    def test_double_unsubscribe(self) -> None:
        session = AgentSessionBase(_make_config())
        seen: list = []

        def listener(evt: Any) -> None:
            seen.append(evt)

        unsubscribe = session.subscribe(listener)
        unsubscribe()
        unsubscribe()  # should not raise
        session.emit({"type": "a"})
        assert seen == []


# ============================================================================
# Write-lock helper
# ============================================================================


class TestRunWithSessionWriteLock:
    @pytest.mark.asyncio
    async def test_runs_without_lock(self) -> None:
        session = AgentSessionBase(_make_config())
        result = await session.run_with_session_write_lock(
            lambda: "ok"
        )
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_runs_async_without_lock(self) -> None:
        session = AgentSessionBase(_make_config())

        async def task() -> str:
            return "async-ok"

        result = await session.run_with_session_write_lock(task)
        assert result == "async-ok"

    @pytest.mark.asyncio
    async def test_runs_with_lock(self) -> None:
        calls: list = []

        async def with_lock(run) -> Any:
            calls.append("locked")
            # The OpenClaw source's
            # ``withSessionWriteLock`` receives
            # a ``run`` callback and is
            # expected to return its result
            # (awaitable or plain). The Python
            # port's ``runWithSessionWriteLock``
            # just delegates, so the lock
            # function is responsible for
            # awaiting the callback.
            result = run()
            if hasattr(result, "__await__"):
                return await result
            return result

        config = _make_config(with_session_write_lock=with_lock)
        session = AgentSessionBase(config)
        result = await session.run_with_session_write_lock(
            lambda: "locked-ok"
        )
        assert result == "locked-ok"
        assert calls == ["locked"]


# ============================================================================
# BuildSystemPromptOptions
# ============================================================================


class TestBuildSystemPromptOptions:
    def test_defaults(self) -> None:
        opts = BuildSystemPromptOptions()
        assert opts.cwd == ""
        assert opts.agent_dir == ""
        assert opts.has_append_system_prompt is False
        assert opts.include_skills is True
        assert opts.include_agents_files is True
        assert opts.include_project_context is True

    def test_construction(self) -> None:
        opts = BuildSystemPromptOptions(
            cwd="/proj",
            agent_dir="/agent",
            has_append_system_prompt=True,
        )
        assert opts.cwd == "/proj"
        assert opts.agent_dir == "/agent"
        assert opts.has_append_system_prompt is True


# ============================================================================
# ToolDefinitionEntry
# ============================================================================


class TestToolDefinitionEntry:
    def test_defaults(self) -> None:
        entry = ToolDefinitionEntry(definition={"name": "x"}, sourceInfo={})
        assert entry.definition == {"name": "x"}
        assert entry.sourceInfo == {}


# ============================================================================
# ActiveToolPromptMetadata
# ============================================================================


class TestActiveToolPromptMetadata:
    def test_defaults(self) -> None:
        meta = ActiveToolPromptMetadata()
        assert meta.valid_tool_names == []
        assert meta.tool_snippets == {}
        assert meta.prompt_guidelines == []

    def test_construction(self) -> None:
        meta = ActiveToolPromptMetadata(
            valid_tool_names=["a", "b"],
            tool_snippets={"a": "snippet"},
            prompt_guidelines=["rule 1"],
        )
        assert meta.valid_tool_names == ["a", "b"]
        assert meta.tool_snippets["a"] == "snippet"
        assert meta.prompt_guidelines == ["rule 1"]


# ============================================================================
# Auth helpers
# ============================================================================


class TestGetRequiredRequestAuth:
    @pytest.mark.asyncio
    async def test_raises_when_no_key(self) -> None:
        class FakeRegistry:
            async def get_api_key_and_headers(self, model):
                return {"ok": False, "error": "No API key found for x"}

            def is_using_oauth(self, model):
                return False

        config = _make_config(model_registry=FakeRegistry())  # type: ignore[arg-type]
        session = AgentSessionBase(config)
        with pytest.raises(RuntimeError) as exc:
            await session.get_required_request_auth("x")  # type: ignore[arg-type]
        assert "No API key" in str(exc.value)

    @pytest.mark.asyncio
    async def test_returns_key_when_present(self) -> None:
        class FakeRegistry:
            async def get_api_key_and_headers(self, model):
                return {
                    "ok": True,
                    "apiKey": "sk-test",
                    "headers": {"X-Foo": "bar"},
                }

            def is_using_oauth(self, model):
                return False

        config = _make_config(model_registry=FakeRegistry())  # type: ignore[arg-type]
        session = AgentSessionBase(config)
        result = await session.get_required_request_auth("x")  # type: ignore[arg-type]
        assert result == {"apiKey": "sk-test", "headers": {"X-Foo": "bar"}}


class TestGetCompactionRequestAuth:
    @pytest.mark.asyncio
    async def test_returns_empty_on_no_key(self) -> None:
        class FakeRegistry:
            async def get_api_key_and_headers(self, model):
                return {"ok": False, "error": "boom"}

        config = _make_config(model_registry=FakeRegistry())  # type: ignore[arg-type]
        session = AgentSessionBase(config)
        result = await session.get_compaction_request_auth("x")  # type: ignore[arg-type]
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_key(self) -> None:
        class FakeRegistry:
            async def get_api_key_and_headers(self, model):
                return {"ok": True, "apiKey": "sk-test", "headers": {}}

        config = _make_config(model_registry=FakeRegistry())  # type: ignore[arg-type]
        session = AgentSessionBase(config)
        result = await session.get_compaction_request_auth("x")  # type: ignore[arg-type]
        assert result == {"apiKey": "sk-test", "headers": {}}


# ============================================================================
# Tool hooks
# ============================================================================


class TestInstallAgentToolHooks:
    def test_no_op_stub(self) -> None:
        session = AgentSessionBase(_make_config())
        # Stub returns None — the full
        # implementation lands with the
        # extensions subclass in 6.12e.
        assert session.install_agent_tool_hooks() is None
