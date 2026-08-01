"""Phase 6.12g — agent_session_compaction tests.

Verifies the public surface of
:class:`AgentSessionCompaction`:

- :meth:`compact` /
  :meth:`abort_compaction` /
  :meth:`abort_branch_summary`
- :meth:`check_compaction` (overflow
  + threshold + skip + skipped
  cases)
- :attr:`auto_compaction_enabled` /
  :meth:`set_auto_compaction_enabled`
- Module-level helpers:
  :func:`_should_compact` /
  :func:`_calculate_context_tokens` /
  :func:`_estimate_context_tokens` /
  :func:`_preflight_manual_session_compaction`
- Constructor / inheritance
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from src.agents.sessions.agent_session_compaction import (
    AgentSessionCompaction,
    CompactionReason,
    CompactionWorkOutcome,
    _calculate_context_tokens,
    _estimate_context_tokens,
    _preflight_manual_session_compaction,
    _should_compact,
)
from src.agents.sessions.agent_session_inspection import (
    AgentSessionInspection,
)


# ============================================================================
# Fakes
# ============================================================================


class _NS:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class FakeAgent:
    def __init__(self) -> None:
        self.state: Any = _NS(
            model=None,
            messages=[],
            thinkingLevel="medium",
            systemPrompt="",
            steeringMode="one-at-a-time",
            followUpMode="one-at-a-time",
        )
        self.steeringMode = "one-at-a-time"
        self.followUpMode = "one-at-a-time"
        self.signal: Any = None
        self.queued: int = 0

    def has_queued_messages(self) -> bool:
        return self.queued > 0

    async def wait_for_idle(self) -> None:
        return None

    def subscribe_events(self, _handler: Any) -> Any:
        return lambda: None

    # OpenClaw's `agent.continue()` becomes `continue_run` in Python (the
    # `continue` keyword can't be a method name).
    def continue_run(self) -> None:
        pass

    def clear_all_queues(self) -> None:
        self.queued = 0

    def abort(self, _reason: Any = None) -> None:
        pass


class FakeRegistry:
    def has_configured_auth(self, model: Any) -> bool:
        return True

    def get_available(self) -> list:
        return []

    def refresh(self) -> None:
        pass


class FakeSettingsManager:
    def __init__(self) -> None:
        self.compaction_enabled: bool = True
        self.threshold: float = 0.85
        self.keep_recent_tokens: int = 20000

    def get_compaction_enabled(self) -> bool:
        return self.compaction_enabled

    def set_compaction_enabled(self, enabled: bool) -> None:
        self.compaction_enabled = enabled

    def get_compaction_settings(self) -> dict:
        return {
            "enabled": self.compaction_enabled,
            "threshold": self.threshold,
            "keepRecentTokens": self.keep_recent_tokens,
        }

    def get_retry_enabled(self) -> bool:
        return True

    def get_retry_max_attempts(self) -> int:
        return 3

    def get_retry_base_delay_ms(self) -> int:
        return 1000

    def get_retry_settings(self) -> dict:
        return {
            "enabled": True,
            "maxRetries": 3,
            "baseDelayMs": 1000,
        }

    def set_retry_enabled(self, enabled: bool) -> None:
        pass

    def get_default_thinking_level(self) -> str:
        return "medium"

    def get_shell_path(self) -> str | None:
        return None

    def get_shell_command_prefix(self) -> str | None:
        return None

    def get_steering_mode(self) -> str:
        return "all"

    def get_follow_up_mode(self) -> str:
        return "all"

    def reload(self) -> _NS:
        async def _do_reload() -> None:
            return None
        return _do_reload()


class FakeSessionManager:
    def __init__(self) -> None:
        self.appended: list = []
        self.session_id: str = "sess-1"
        self.session_name: str | None = None
        self.session_file: str | None = "/tmp/sess.jsonl"
        self.cwd: str = "/tmp/proj"
        self.leaf_id: str = "leaf-x"
        self.branch: list = []
        self.entries: list = []
        self.built_ctx: dict = {"messages": []}
        self.compactions: list = []

    def get_branch(self) -> list:
        return list(self.branch)

    def get_entries(self) -> list:
        return list(self.entries)

    def get_leaf_id(self) -> str:
        return self.leaf_id

    def build_session_context(self) -> dict:
        return dict(self.built_ctx)

    def append_compaction(
        self,
        summary: str,
        first_kept_entry_id: Any,
        tokens_before: Any,
        details: Any,
        from_extension: bool,
    ) -> None:
        self.compactions.append({
            "summary": summary,
            "firstKeptEntryId": first_kept_entry_id,
            "tokensBefore": tokens_before,
            "details": details,
            "fromExtension": from_extension,
        })

    def append_message(self, message: Any) -> None:
        self.appended.append(message)

    def get_session_id(self) -> str:
        return self.session_id

    def get_session_name(self) -> str | None:
        return self.session_name

    def get_session_file(self) -> str | None:
        return self.session_file

    def get_cwd(self) -> str:
        return self.cwd


class FakeResourceLoader:
    def __init__(self) -> None:
        self.extensions: list = []
        self.runtime: Any = _NS(
            flagValues={},
            pendingProviderRegistrations=[],
        )

    def get_extensions(self) -> _NS:
        return _NS(
            extensions=list(self.extensions),
            runtime=self.runtime,
            errors=[],
        )

    def get_skills(self) -> dict:
        return {"skills": [], "diagnostics": []}

    def get_prompts(self) -> dict:
        return {"prompts": [], "diagnostics": []}

    def get_themes(self) -> dict:
        return {"themes": [], "diagnostics": []}

    def get_system_prompt(self) -> str | None:
        return None

    def get_append_system_prompt(self) -> list:
        return []

    def get_agents_files(self) -> dict:
        return {"agentsFiles": [], "diagnostics": []}

    def extend_resources(self, _paths: dict) -> None:
        pass

    def reload(self) -> _NS:
        async def _do_reload() -> None:
            return None
        return _do_reload()


class FakeExtensionRunner:
    def __init__(self) -> None:
        self.events: list = []
        self.handlers: dict = {}

    def has_handlers(self, t: str) -> bool:
        return bool(self.handlers.get(t))

    async def emit(self, event: dict) -> Any:
        self.events.append(event)
        # For session_before_compact, can
        # return a result dict.
        if event.get("type") == "session_before_compact":
            return None
        return None

    def set_ui_context(self, _ctx: Any) -> None:
        pass

    def bind_command_context(self, _ctx: Any) -> None:
        pass

    def on_error(self, _listener: Any) -> Any:
        return lambda: None

    def get_flag_values(self) -> dict:
        return {}

    def get_registered_commands(self) -> list:
        return []


def _make_session(
    *,
    settings: Any | None = None,
    session_manager: Any | None = None,
    model: Any | None = None,
    extension_runner: Any | None = None,
) -> AgentSessionCompaction:
    import tempfile

    agent = FakeAgent()
    config = _NS(
        agent=agent,
        session_manager=session_manager or FakeSessionManager(),
        settings_manager=settings or FakeSettingsManager(),
        scoped_models=[],
        custom_tools=[],
        cwd=tempfile.mkdtemp(),
        resource_loader=FakeResourceLoader(),
        model_registry=FakeRegistry(),
        extension_runner_ref=None,
        initial_active_tool_names=None,
        allowed_tool_names=None,
        disable_built_in_tools=False,
        base_tools_override=None,
        session_start_event=None,
        with_session_write_lock=None,
    )
    session = AgentSessionCompaction(config)
    if model is not None:
        session.model = model
    if extension_runner is not None:
        session.current_extension_runner = extension_runner
    return session


# ============================================================================
# Module-level helpers
# ============================================================================


class TestShouldCompact:
    def test_disabled(self) -> None:
        assert _should_compact(1000, 1000, {"enabled": False}) is False

    def test_below_threshold(self) -> None:
        assert _should_compact(500, 1000, {"enabled": True}) is False

    def test_at_threshold(self) -> None:
        assert _should_compact(850, 1000, {"enabled": True}) is True

    def test_no_context_window(self) -> None:
        # No context window → can't tell.
        assert _should_compact(1000, 0, {"enabled": True}) is False

    def test_default_threshold(self) -> None:
        # No threshold in settings → use
        # default 0.85.
        assert _should_compact(850, 1000, {"enabled": True}) is True
        assert _should_compact(840, 1000, {"enabled": True}) is False


class TestCalculateContextTokens:
    def test_empty(self) -> None:
        assert _calculate_context_tokens({}) == 0

    def test_basic(self) -> None:
        usage = {
            "input": 100,
            "output": 50,
            "cacheRead": 10,
            "cacheWrite": 5,
        }
        assert _calculate_context_tokens(usage) == 165

    def test_missing_fields(self) -> None:
        assert _calculate_context_tokens({"input": 100}) == 100


class TestEstimateContextTokens:
    def test_empty(self) -> None:
        result = _estimate_context_tokens([])
        assert result["tokens"] == 0
        assert result["lastUsageIndex"] is None

    def test_with_assistant_usage(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "hello",
                "usage": {
                    "input": 100,
                    "output": 50,
                },
            },
        ]
        result = _estimate_context_tokens(messages)
        assert result["tokens"] > 0
        assert result["lastUsageIndex"] == 1


class TestPreflightManualSessionCompaction:
    def test_empty_path(self) -> None:
        result = _preflight_manual_session_compaction([], {})
        assert result["compactable"] is False
        assert "reason" in result

    def test_with_entries(self) -> None:
        result = _preflight_manual_session_compaction(
            [{"id": "a"}, {"id": "b"}],
            {"enabled": True, "threshold": 0.85},
        )
        assert result["compactable"] is True
        assert "preparation" in result


# ============================================================================
# Constructor / inheritance
# ============================================================================


class TestConstructor:
    def test_inherits_inspection(self) -> None:
        session = _make_session()
        assert isinstance(session, AgentSessionInspection)


# ============================================================================
# auto_compaction_enabled + set_auto_compaction_enabled
# ============================================================================


class TestAutoCompactionEnabled:
    def test_enabled(self) -> None:
        session = _make_session()
        assert session.auto_compaction_enabled is True

    def test_disabled(self) -> None:
        settings = FakeSettingsManager()
        settings.compaction_enabled = False
        session = _make_session(settings=settings)
        assert session.auto_compaction_enabled is False

    def test_set(self) -> None:
        settings = FakeSettingsManager()
        session = _make_session(settings=settings)
        session.set_auto_compaction_enabled(False)
        assert settings.compaction_enabled is False
        session.set_auto_compaction_enabled(True)
        assert settings.compaction_enabled is True


# ============================================================================
# abort_compaction + abort_branch_summary
# ============================================================================


class TestAbortCompaction:
    def test_idle(self) -> None:
        session = _make_session()
        session.abort_compaction()  # no-op
        assert session.compaction_abort_controller is None
        assert session.auto_compaction_abort_controller is None

    def test_in_progress(self) -> None:
        session = _make_session()
        ctrl1 = _NS(aborted=False)
        ctrl1.abort = lambda: setattr(ctrl1, "aborted", True)
        ctrl2 = _NS(aborted=False)
        ctrl2.abort = lambda: setattr(ctrl2, "aborted", True)
        session.compaction_abort_controller = ctrl1
        session.auto_compaction_abort_controller = ctrl2
        session.abort_compaction()
        assert ctrl1.aborted is True
        assert ctrl2.aborted is True


class TestAbortBranchSummary:
    def test_idle(self) -> None:
        session = _make_session()
        session.abort_branch_summary()  # no-op
        assert session.branch_summary_abort_controller is None

    def test_in_progress(self) -> None:
        session = _make_session()
        ctrl = _NS(aborted=False)
        ctrl.abort = lambda: setattr(ctrl, "aborted", True)
        session.branch_summary_abort_controller = ctrl
        session.abort_branch_summary()
        assert ctrl.aborted is True


# ============================================================================
# compact (manual)
# ============================================================================


class TestCompact:
    @pytest.mark.asyncio
    async def test_no_model(self) -> None:
        session = _make_session()
        # No model → manual compaction
        # raises.
        with pytest.raises(RuntimeError, match="model"):
            await session.compact()

    @pytest.mark.asyncio
    async def test_no_branch(self) -> None:
        # The OpenClaw source's manual
        # preflight returns ``not
        # compactable`` for an empty
        # path. The Python port's
        # STUB compaction returns
        # ``skipped`` (no preparation)
        # for empty branch.
        session = _make_session(model={"provider": "x", "id": "y"})
        with pytest.raises(RuntimeError, match="(No session entries|Compaction)"):
            await session.compact()

    @pytest.mark.asyncio
    async def test_emits_start_event(self) -> None:
        sm = FakeSessionManager()
        sm.branch = [{"id": "a"}]
        runner = FakeExtensionRunner()
        session = _make_session(
            session_manager=sm,
            model={"provider": "x", "id": "y"},
            extension_runner=runner,
        )
        listener_events: list = []
        session.subscribe(listener_events.append)
        # The compact() call returns
        # ``skipped`` (no real runtime) →
        # raises RuntimeError.
        with pytest.raises(RuntimeError):
            await session.compact()
        # The compaction_start event was
        # emitted.
        start_events = [
            e for e in listener_events
            if isinstance(e, dict) and e.get("type") == "compaction_start"
        ]
        assert len(start_events) == 1
        assert start_events[0]["reason"] == "manual"

    @pytest.mark.asyncio
    async def test_emits_end_event_on_skip(self) -> None:
        sm = FakeSessionManager()
        sm.branch = [{"id": "a"}]
        session = _make_session(
            session_manager=sm,
            model={"provider": "x", "id": "y"},
        )
        listener_events: list = []
        session.subscribe(listener_events.append)
        with pytest.raises(RuntimeError):
            await session.compact()
        end_events = [
            e for e in listener_events
            if e.get("type") == "compaction_end"
        ]
        assert len(end_events) == 1
        assert end_events[0]["aborted"] is True


# ============================================================================
# check_compaction
# ============================================================================


class TestCheckCompaction:
    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        settings = FakeSettingsManager()
        settings.compaction_enabled = False
        session = _make_session(settings=settings)
        result = await session.check_compaction(
            {"stopReason": "stop", "content": "hi"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_skip_aborted(self) -> None:
        session = _make_session()
        result = await session.check_compaction(
            {"stopReason": "aborted", "content": "hi"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_skip_pre_compaction_message(self) -> None:
        # Add a compaction entry.
        sm = FakeSessionManager()
        sm.branch = [
            {
                "id": "c1",
                "type": "compaction",
                "summary": "old",
                "timestamp": 1000,
            },
            {
                "id": "m1",
                "type": "message",
                "message": {
                    "role": "assistant",
                    "stopReason": "stop",
                    "content": "hi",
                    "timestamp": 500,  # BEFORE compaction
                },
            },
        ]
        # The check_compaction walks
        # branch but the OpenClaw
        # source uses
        # ``get_latest_compaction_entry``
        # on ``getBranch()`` — and our
        # port has a fallback to
        # ``get_entries()``. Build entries
        # too.
        sm.entries = list(sm.branch)
        session = _make_session(
            session_manager=sm,
            model={
                "provider": "anthropic",
                "id": "claude",
                "contextWindow": 1000,
            },
        )
        session.agent.state.messages = [
            {
                "role": "assistant",
                "stopReason": "stop",
                "content": "hi",
                "timestamp": 500,
            },
        ]
        result = await session.check_compaction(
            {
                "role": "assistant",
                "stopReason": "stop",
                "content": "hi",
                "provider": "anthropic",
                "model": "claude",
                "timestamp": 500,
            }
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_model(self) -> None:
        # No model → no threshold check
        # possible → return False.
        session = _make_session()
        result = await session.check_compaction(
            {"stopReason": "stop", "content": "hi"}
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_overflow_recovery_disabled(self) -> None:
        """Overflow case: when the LLM
        returns a context-overflow
        error, the session attempts a
        compact-and-retry. The Python
        port's STUB compaction work
        returns ``skipped`` for
        branches that don't have the
        real runtime — so the test
        verifies the flow doesn't
        raise."""
        model = {
            "provider": "anthropic",
            "id": "claude",
            "contextWindow": 1000,
        }
        sm = FakeSessionManager()
        sm.branch = [
            {
                "id": "u1",
                "type": "message",
                "message": {
                    "role": "user",
                    "content": "hi",
                },
            },
        ]
        session = _make_session(
            session_manager=sm, model=model
        )
        session.agent.state.messages = [
            {
                "role": "assistant",
                "stopReason": "error",
                "errorMessage": "context length exceeded",
                "content": [],
            },
        ]
        result = await session.check_compaction(
            {
                "role": "assistant",
                "provider": "anthropic",
                "model": "claude",
                "stopReason": "error",
                "errorMessage": "context length exceeded",
                "content": [],
            }
        )
        # STUB returns False (skipped
        # because no real runtime).
        # Important: no exception.
        assert result is False
        # ``overflow_recovery_attempted``
        # was set.
        assert session.overflow_recovery_attempted is True

    @pytest.mark.asyncio
    async def test_overflow_recovery_already_attempted(self) -> None:
        model = {
            "provider": "anthropic",
            "id": "claude",
            "contextWindow": 1000,
        }
        session = _make_session(model=model)
        session.overflow_recovery_attempted = True
        # Listener for the error event.
        events: list = []
        session.subscribe(events.append)
        result = await session.check_compaction(
            {
                "role": "assistant",
                "provider": "anthropic",
                "model": "claude",
                "stopReason": "error",
                "errorMessage": "context length exceeded",
                "content": [],
            }
        )
        assert result is False
        # An error event was emitted.
        err_events = [
            e for e in events
            if e.get("type") == "compaction_end"
            and "errorMessage" in e
        ]
        assert len(err_events) == 1

    @pytest.mark.asyncio
    async def test_threshold_not_met(self) -> None:
        model = {
            "provider": "anthropic",
            "id": "claude",
            "contextWindow": 100000,
        }
        session = _make_session(model=model)
        result = await session.check_compaction(
            {
                "role": "assistant",
                "provider": "anthropic",
                "model": "claude",
                "stopReason": "stop",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {
                    "input": 100,
                    "output": 50,
                },
            }
        )
        # 150 / 100000 = 0.0015 < 0.85
        # → no compaction.
        assert result is False

    @pytest.mark.asyncio
    async def test_threshold_met(self) -> None:
        model = {
            "provider": "anthropic",
            "id": "claude",
            "contextWindow": 1000,
        }
        session = _make_session(model=model)
        result = await session.check_compaction(
            {
                "role": "assistant",
                "provider": "anthropic",
                "model": "claude",
                "stopReason": "stop",
                "content": [{"type": "text", "text": "hi"}],
                "usage": {
                    "input": 900,
                    "output": 50,
                },
            }
        )
        # 950 / 1000 = 0.95 > 0.85 →
        # compaction attempted. STUB
        # returns False (skipped).
        # Important: no exception.
        assert result is False

    @pytest.mark.asyncio
    async def test_different_model_skips_overflow(self) -> None:
        """The OpenClaw source skips the
        overflow check if the message
        came from a different model."""
        model = {
            "provider": "anthropic",
            "id": "claude-3",
            "contextWindow": 1000,
        }
        session = _make_session(model=model)
        result = await session.check_compaction(
            {
                "role": "assistant",
                "provider": "openai",
                "model": "gpt-4",
                "stopReason": "error",
                "errorMessage": "context length exceeded",
                "content": [],
            }
        )
        # Different model → no overflow
        # check; falls through to
        # threshold.
        # Threshold can't be calculated
        # (stopReason=error, no usage)
        # → return False.
        assert result is False


# ============================================================================
# disconnect_from_agent / reconnect_to_agent
# ============================================================================


class TestDisconnectReconnect:
    def test_disconnect_idle(self) -> None:
        session = _make_session()
        # No-op when not connected.
        session.disconnect_from_agent()
        assert session.unsubscribe_agent is None

    def test_disconnect_when_connected(self) -> None:
        session = _make_session()
        called: list = []

        def _unsub() -> None:
            called.append("unsub")

        session.unsubscribe_agent = _unsub
        session.disconnect_from_agent()
        assert called == ["unsub"]
        assert session.unsubscribe_agent is None

    def test_reconnect_when_already_connected(self) -> None:
        session = _make_session()

        def _unsub() -> None:
            pass

        session.unsubscribe_agent = _unsub
        session.reconnect_to_agent()  # no-op
        # Still connected.
        assert session.unsubscribe_agent is _unsub

    def test_reconnect_subscribes(self) -> None:
        session = _make_session()
        # FakeAgent has subscribe_events.
        session.reconnect_to_agent()
        # The agent was subscribed.
        assert session.unsubscribe_agent is not None


# ============================================================================
# Re-exports
# ============================================================================


class TestReExports:
    def test_compaction_reason(self) -> None:
        assert CompactionReason is str

    def test_work_outcome(self) -> None:
        assert CompactionWorkOutcome is dict
