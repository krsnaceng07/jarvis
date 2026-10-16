"""Phase 7.1 — embedded_agent_runner orchestrator + loop + registry tests.

Verifies the public surface of
the 7.1 modules:

- :func:`run_embedded_agent` —
  the public entrypoint.
- :func:`run_prepared_embedded_loop` —
  the main loop.
- :class:`PreparedEmbeddedRunInput` —
  the loop input.
- :mod:`run.params` /
  :mod:`run.internal_params` —
  parameter TypedDicts.
- :mod:`runs` — the run registry
  (active-run tracking + queue
  message outcomes + abandonment).
"""
from __future__ import annotations

import pytest

from src.agents.embedded_agent_runner import (
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    ACTIVE_EMBEDDED_RUNS,
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    EmbeddedAgentQueueMessageOutcome,
    PreparedEmbeddedRunInput,
    RunEmbeddedAgentInternalParams,
    RunEmbeddedAgentParams,
    RunEmbeddedAgentParamsWithSessionFile,
    abort_active_embedded_run,
    clear_embedded_agent_run_abortability_for_run_id,
    execute_prepared_embedded_run,
    format_embedded_agent_queue_failure_summary,
    is_embedded_agent_run_abortable_for_run_id,
    is_embedded_run_abandoned,
    mark_active_embedded_run_abandoned,
    queue_embedded_agent_message_with_outcome,
    queue_embedded_agent_message_with_outcome_async,
    register_active_embedded_run,
    retain_embedded_agent_run_abortability_for_run_id,
    run_embedded_agent,
    run_prepared_embedded_loop,
    unregister_active_embedded_run,
)
from src.agents.embedded_agent_runner.run_orchestrator import (
    capture_agent_run_lifecycle_generation,
    get_agent_event_lifecycle_generation,
    with_agent_run_lifecycle_generation,
)
from src.agents.embedded_agent_runner.run.internal_params import (
    RunEmbeddedAgentInternalParams as InternalParams,
)
from src.agents.embedded_agent_runner.run.params import (
    RunEmbeddedAgentParams as PublicParams,
)


# ============================================================================
# Params TypedDicts
# ============================================================================


class TestRunEmbeddedAgentParams:
    def test_constructible_from_dict(self) -> None:
        params: RunEmbeddedAgentParams = {
            "sessionId": "sess-1",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
            "prompt": "Hello",
        }
        assert params["sessionId"] == "sess-1"

    def test_optional_fields(self) -> None:
        params: RunEmbeddedAgentParams = {}
        # All fields are optional.
        assert "sessionId" not in params

    def test_internal_params_extends(self) -> None:
        params: RunEmbeddedAgentInternalParams = {
            "sessionId": "sess-1",
            "onSuccessfulAuthBinding": "cb",
            "authProfileStateMode": "read-only",
        }
        assert params["sessionId"] == "sess-1"
        assert params["onSuccessfulAuthBinding"] == "cb"

    def test_internal_aliases(self) -> None:
        # The re-exported classes
        # match the public aliases.
        assert InternalParams is RunEmbeddedAgentInternalParams
        assert PublicParams is RunEmbeddedAgentParams

    def test_session_file_extends(self) -> None:
        params: RunEmbeddedAgentParamsWithSessionFile = {
            "sessionId": "sess-1",
            "sessionFile": "/path/to/sess.jsonl",
        }
        assert params["sessionFile"] == "/path/to/sess.jsonl"


# ============================================================================
# PreparedEmbeddedRunInput
# ============================================================================


class TestPreparedEmbeddedRunInput:
    def test_construct(self) -> None:
        run_params: RunEmbeddedAgentParamsWithSessionFile = {
            "sessionId": "sess-1",
            "sessionFile": "/tmp/sess.jsonl",
        }
        input = PreparedEmbeddedRunInput(
            run_params=run_params,
            provider="anthropic",
            model_id="claude-3-5-sonnet",
            agent_dir="/tmp/agent",
            workspace_dir="/tmp/proj",
            is_canonical_workspace=True,
            global_lane="main",
            resolved_session_key="key-1",
            resolved_tool_result_format="markdown",
            started_at_ms=1000,
        )
        assert input.provider == "anthropic"
        assert input.model_id == "claude-3-5-sonnet"
        assert input.started_at_ms == 1000

    def test_to_dict(self) -> None:
        run_params: RunEmbeddedAgentParamsWithSessionFile = {
            "sessionId": "sess-1",
        }
        input = PreparedEmbeddedRunInput(
            run_params=run_params,
            provider="anthropic",
            model_id="claude-3-5-sonnet",
            agent_dir="",
            workspace_dir="/tmp/proj",
        )
        d = input.to_dict()
        assert d["provider"] == "anthropic"
        assert d["modelId"] == "claude-3-5-sonnet"
        assert d["workspaceDir"] == "/tmp/proj"


# ============================================================================
# Run registry (runs)
# ============================================================================


def _make_handle(
    run_id: str = "run-1",
    abortable: bool = True,
) -> dict:
    """Build a minimal queue-handle
    dict for tests."""
    return {
        "runId": run_id,
        "isAbortable": lambda: abortable,
        "isStreaming": lambda: True,
        "abort": lambda reason=None: None,
        "queueMessage": lambda text, options=None: None,
    }


def _reset_run_state() -> None:
    """Reset the singleton run-state
    maps."""
    ACTIVE_EMBEDDED_RUNS.clear()
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID.clear()
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.clear()
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.clear()
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID.clear()
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY.clear()
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE.clear()


class TestRegisterUnregister:
    def setup_method(self) -> None:
        _reset_run_state()

    def test_register(self) -> None:
        handle = _make_handle()
        register_active_embedded_run(
            "sess-1", handle, "key-1", "/path/sess.jsonl"
        )
        assert ACTIVE_EMBEDDED_RUNS["sess-1"] is handle
        assert ACTIVE_EMBEDDED_RUNS_BY_RUN_ID["run-1"] is handle
        assert (
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY["key-1"] == "sess-1"
        )
        assert (
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE[
                _resolved_key("/path/sess.jsonl")
            ]
            == "sess-1"
        )

    def test_unregister(self) -> None:
        handle = _make_handle()
        register_active_embedded_run(
            "sess-1", handle, "key-1", "/path/sess.jsonl"
        )
        unregister_active_embedded_run(
            "sess-1", handle, "key-1", "/path/sess.jsonl"
        )
        assert "sess-1" not in ACTIVE_EMBEDDED_RUNS
        assert "run-1" not in ACTIVE_EMBEDDED_RUNS_BY_RUN_ID
        assert "key-1" not in (
            ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY
        )

    def test_register_empty_session_id(self) -> None:
        handle = _make_handle()
        register_active_embedded_run("", handle)
        # Empty session id → no-op.
        assert "sess-1" not in ACTIVE_EMBEDDED_RUNS


def _resolved_key(path: str) -> str:
    """Resolve the embedded session
    file key (uses realpath)."""
    from src.agents.embedded_agent_runner import (
        resolve_embedded_session_file_key,
    )
    return resolve_embedded_session_file_key(path)


class TestAbandonment:
    def setup_method(self) -> None:
        _reset_run_state()

    def test_mark_abandoned(self) -> None:
        handle = _make_handle()
        register_active_embedded_run(
            "sess-1", handle, "key-1", "/path/sess.jsonl"
        )
        result = mark_active_embedded_run_abandoned(
            "sess-1",
            handle,
            "key-1",
            "/path/sess.jsonl",
            reason="timeout",
        )
        assert result is True
        assert "sess-1" in ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID

    def test_mark_abandoned_wrong_handle(self) -> None:
        handle = _make_handle()
        register_active_embedded_run("sess-1", handle)
        # Different handle → returns False.
        result = mark_active_embedded_run_abandoned(
            "sess-1", {"different": "handle"}
        )
        assert result is False

    def test_is_abandoned(self) -> None:
        handle = _make_handle()
        register_active_embedded_run(
            "sess-1", handle, "key-1", "/path/sess.jsonl"
        )
        mark_active_embedded_run_abandoned(
            "sess-1", handle, "key-1", "/path/sess.jsonl"
        )
        assert is_embedded_run_abandoned(session_id="sess-1")
        assert is_embedded_run_abandoned(session_key="key-1")
        assert is_embedded_run_abandoned(
            session_file="/path/sess.jsonl"
        )

    def test_is_abandoned_unknown(self) -> None:
        assert is_embedded_run_abandoned() is False
        assert is_embedded_run_abandoned(session_id="unknown") is False


class TestAbortability:
    def setup_method(self) -> None:
        _reset_run_state()

    def test_abortable_by_run_id(self) -> None:
        handle = _make_handle(abortable=True)
        register_active_embedded_run("sess-1", handle)
        assert (
            is_embedded_agent_run_abortable_for_run_id("run-1")
            is True
        )

    def test_not_abortable(self) -> None:
        handle = _make_handle(abortable=False)
        register_active_embedded_run("sess-1", handle)
        assert (
            is_embedded_agent_run_abortable_for_run_id("run-1")
            is False
        )

    def test_unknown_run_id(self) -> None:
        # No active run → returns True.
        assert (
            is_embedded_agent_run_abortable_for_run_id("unknown")
            is True
        )

    def test_clear_abortability(self) -> None:
        handle = _make_handle()
        register_active_embedded_run("sess-1", handle)
        clear_embedded_agent_run_abortability_for_run_id("run-1")
        assert "run-1" not in ACTIVE_EMBEDDED_RUNS_BY_RUN_ID

    def test_retain_abortability(self) -> None:
        from src.agents.embedded_agent_runner import (
            RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS,
        )
        retain_embedded_agent_run_abortability_for_run_id("run-1")
        assert "run-1" in RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS


class TestLifecycleConfigParity:
    def test_runtime_config_and_lifecycle_generation_are_resolved(self, monkeypatch) -> None:
        captured: list[dict] = []

        async def fake_loop(input: PreparedEmbeddedRunInput) -> dict:
            captured.append(
                {
                    "provider": input.provider,
                    "modelId": input.model_id,
                    "config": input.run_params.get("config"),
                    "lifecycleGeneration": input.lifecycle_generation,
                }
            )
            return {"meta": {}}

        monkeypatch.setattr(
            "src.agents.embedded_agent_runner.run_orchestrator.get_runtime_config_snapshot",
            lambda: {"provider": "anthropic", "model": "claude-3-5-sonnet"},
        )
        monkeypatch.setattr(
            "src.agents.embedded_agent_runner.run_orchestrator.run_prepared_embedded_loop",
            fake_loop,
        )

        result = run_embedded_agent(
            {
                "runId": "run-123",
                "prompt": "Hello",
            }
        )

        assert result["meta"] == {}
        assert len(captured) == 1
        assert captured[0]["provider"] == "anthropic"
        assert captured[0]["modelId"] == "claude-3-5-sonnet"
        assert captured[0]["config"] == {
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
        }
        assert captured[0]["lifecycleGeneration"] >= 1

    def test_lifecycle_generation_helpers(self) -> None:
        generation = capture_agent_run_lifecycle_generation("run-abc")
        assert generation >= 1
        assert get_agent_event_lifecycle_generation() == generation

        with with_agent_run_lifecycle_generation(generation + 1):
            assert get_agent_event_lifecycle_generation() == generation + 1

        assert get_agent_event_lifecycle_generation() == generation


class TestAbort:
    def setup_method(self) -> None:
        _reset_run_state()

    def test_abort_active_run(self) -> None:
        called: list = []
        handle = {
            "runId": "run-1",
            "isAbortable": lambda: True,
            "isStreaming": lambda: True,
            "abort": lambda reason=None: called.append(reason),
            "queueMessage": lambda text, options=None: None,
        }
        register_active_embedded_run("sess-1", handle)
        result = abort_active_embedded_run("sess-1", reason="user_abort")
        assert result is True
        assert called == ["user_abort"]

    def test_abort_unknown_session(self) -> None:
        result = abort_active_embedded_run("unknown")
        assert result is False

    def test_abort_not_abortable(self) -> None:
        handle = _make_handle(abortable=False)
        register_active_embedded_run("sess-1", handle)
        result = abort_active_embedded_run("sess-1")
        assert result is False


class TestQueueMessage:
    def setup_method(self) -> None:
        _reset_run_state()

    def test_no_active_run(self) -> None:
        result = queue_embedded_agent_message_with_outcome(
            "sess-1", "hello"
        )
        assert result["queued"] is False
        assert result["reason"] == "no_active_run"

    def test_active_run(self) -> None:
        handle = _make_handle()
        register_active_embedded_run("sess-1", handle)
        result = queue_embedded_agent_message_with_outcome(
            "sess-1", "hello"
        )
        assert result["queued"] is True
        assert result["target"] == "embedded_run"

    @pytest.mark.asyncio
    async def test_async_no_active_run(self) -> None:
        result = await queue_embedded_agent_message_with_outcome_async(
            "sess-1", "hello"
        )
        assert result["queued"] is False

    @pytest.mark.asyncio
    async def test_async_active_run(self) -> None:
        handle = _make_handle()
        register_active_embedded_run("sess-1", handle)
        result = await queue_embedded_agent_message_with_outcome_async(
            "sess-1", "hello"
        )
        assert result["queued"] is True


class TestFormatFailureSummary:
    def test_queued(self) -> None:
        outcome: EmbeddedAgentQueueMessageOutcome = {
            "queued": True,
        }
        assert (
            format_embedded_agent_queue_failure_summary(outcome)
            is None
        )

    def test_failure(self) -> None:
        outcome: EmbeddedAgentQueueMessageOutcome = {
            "queued": False,
            "sessionId": "sess-1",
            "reason": "no_active_run",
            "gatewayHealth": "live",
        }
        result = format_embedded_agent_queue_failure_summary(
            outcome
        )
        assert result is not None
        assert "queue_message_failed" in result
        assert "no_active_run" in result
        assert "sess-1" in result

    def test_failure_with_error(self) -> None:
        outcome: EmbeddedAgentQueueMessageOutcome = {
            "queued": False,
            "sessionId": "sess-1",
            "reason": "runtime_rejected",
            "gatewayHealth": "live",
            "errorMessage": "boom",
        }
        result = format_embedded_agent_queue_failure_summary(
            outcome
        )
        assert "boom" in result

    def test_invalid(self) -> None:
        assert (
            format_embedded_agent_queue_failure_summary("not a dict")
            is None
        )


# ============================================================================
# Run loop
# ============================================================================


class TestRunPreparedEmbeddedLoop:
    @pytest.mark.asyncio
    async def test_basic(self) -> None:
        run_params: RunEmbeddedAgentParamsWithSessionFile = {
            "sessionId": "sess-1",
            "sessionFile": "/tmp/sess.jsonl",
            "prompt": "Hello, world!",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
        }
        input = PreparedEmbeddedRunInput(
            run_params=run_params,
            provider="anthropic",
            model_id="claude-3-5-sonnet",
            agent_dir="/tmp/agent",
            workspace_dir="/tmp/proj",
            is_canonical_workspace=True,
            global_lane="main",
            resolved_session_key="key-1",
            resolved_tool_result_format="markdown",
            started_at_ms=0,
        )
        result = await run_prepared_embedded_loop(input)
        assert "meta" in result
        meta = result["meta"]
        assert "durationMs" in meta
        assert meta["agentMeta"]["sessionId"] == "sess-1"
        assert meta["agentMeta"]["provider"] == "anthropic"
        # Phase 7.1 — stub returns a
        # placeholder response.
        assert "Phase 7.1 stub" in meta["finalAssistantVisibleText"]

    @pytest.mark.asyncio
    async def test_empty_prompt(self) -> None:
        run_params: RunEmbeddedAgentParamsWithSessionFile = {
            "sessionId": "sess-1",
            "sessionFile": "/tmp/sess.jsonl",
        }
        input = PreparedEmbeddedRunInput(
            run_params=run_params,
            provider="anthropic",
            model_id="claude-3-5-sonnet",
            agent_dir="/tmp/agent",
            workspace_dir="/tmp/proj",
        )
        result = await run_prepared_embedded_loop(input)
        # Empty prompt → empty
        # response.
        assert result["meta"]["finalAssistantVisibleText"] == ""


# ============================================================================
# Execute prepared (alias)
# ============================================================================


class TestExecutePreparedEmbeddedRun:
    @pytest.mark.asyncio
    async def test_alias(self) -> None:
        run_params: RunEmbeddedAgentParamsWithSessionFile = {
            "sessionId": "sess-1",
            "prompt": "hi",
        }
        input = PreparedEmbeddedRunInput(
            run_params=run_params,
            provider="anthropic",
            model_id="claude-3-5-sonnet",
            agent_dir="",
            workspace_dir="",
        )
        result = await execute_prepared_embedded_run(input)
        assert "meta" in result


# ============================================================================
# Orchestrator (run_embedded_agent)
# ============================================================================


class TestRunEmbeddedAgent:
    @pytest.mark.asyncio
    async def test_basic_dict(self) -> None:
        # The orchestrator accepts a
        # plain dict.
        result = await run_embedded_agent(
            {
                "sessionId": "sess-1",
                "prompt": "Hello",
                "provider": "anthropic",
                "model": "claude-3-5-sonnet",
            }
        )
        assert "meta" in result
        assert result["meta"]["agentMeta"]["sessionId"] == "sess-1"

    @pytest.mark.asyncio
    async def test_internal_params(self) -> None:
        params: RunEmbeddedAgentInternalParams = {
            "sessionId": "sess-1",
            "prompt": "Hello",
            "onSuccessfulAuthBinding": lambda binding: None,
        }
        result = await run_embedded_agent(params)
        assert "meta" in result

    @pytest.mark.asyncio
    async def test_empty_params(self) -> None:
        # None / empty params should
        # still work.
        result = await run_embedded_agent({})
        assert "meta" in result
        # durationMs is set.
        assert result["meta"]["durationMs"] >= 0

    @pytest.mark.asyncio
    async def test_with_workspace(self) -> None:
        result = await run_embedded_agent(
            {
                "sessionId": "sess-1",
                "prompt": "Hello",
                "workspaceDir": "/tmp/proj",
            }
        )
        # Prompt length appears in the
        # stub response.
        assert "Hello" in result["meta"]["finalAssistantVisibleText"]
