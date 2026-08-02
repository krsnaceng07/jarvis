"""Phase 7.0 — embedded_agent_runner foundation tests.

Verifies the public surface of
the foundational types + module
state + small helpers in
:mod:`jarvis.agents.embedded_agent_runner`:

- :class:`BlockReplyFlushContext` /
  :class:`EmbeddedAgentMeta` /
  :class:`EmbeddedAgentRunMeta` /
  :class:`EmbeddedAgentRunResult` /
  :class:`EmbeddedAgentCompactResult` /
  :class:`EmbeddedSandboxInfo` types
- :func:`is_runner_abort_error`
- :func:`is_zero_usage_empty_stop_assistant_turn`
- :func:`resolve_embedded_run_failure_signal` +
  :func:`resolve_failure_signal_code`
- :func:`resolve_embedded_session_file_key`
- :func:`build_embedded_message_action_discovery_input`
- :func:`format_embedded_agent_execution_phase` +
  :data:`EMBEDDED_AGENT_EXECUTION_PHASES`
- Lanes (:class:`CommandLane` + 3
  resolvers)
- Tool allowlist (5 helpers +
  :data:`AGENT_RESERVED_TOOL_NAMES`)
- Run state Maps + 4 getters
- :func:`run_embedded_agent` stub
  (raises :class:`NotImplementedError`)
"""
from __future__ import annotations

import os
import pytest

from src.agents.embedded_agent_runner import (
    ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    ACTIVE_EMBEDDED_RUNS,
    ACTIVE_EMBEDDED_RUNS_BY_RUN_ID,
    ACTIVE_EMBEDDED_RUN_SNAPSHOTS,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE,
    ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY,
    AGENT_RESERVED_TOOL_NAMES,
    BlockReplyFlushContext,
    CommandLane,
    EMBEDDED_AGENT_EXECUTION_PHASES,
    EMBEDDED_AGENT_EXECUTION_PHASE_LABELS,
    EMBEDDED_RUN_WAITERS,
    EmbeddedAgentCompactResult,
    EmbeddedAgentMeta,
    EmbeddedAgentRunMeta,
    EmbeddedAgentRunResult,
    EmbeddedFullAccessBlockedReason,
    EmbeddedRunFailureSignal,
    EmbeddedRunLivenessState,
    EmbeddedSandboxInfo,
    RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS,
    ToolSummaryTrace,
    TraceAttempt,
    build_embedded_message_action_discovery_input,
    collect_allowed_tool_names,
    collect_core_builtin_tool_names,
    collect_registered_tool_names,
    format_embedded_agent_execution_phase,
    get_active_embedded_run_count,
    is_runner_abort_error,
    is_zero_usage_empty_stop_assistant_turn,
    list_active_embedded_run_session_ids,
    list_active_embedded_run_session_keys,
    log,
    resolve_active_embedded_run_session_id,
    resolve_embedded_run_failure_signal,
    resolve_embedded_session_file_key,
    resolve_embedded_session_lane,
    resolve_failure_signal_code,
    resolve_global_lane,
    resolve_session_lane,
    run_embedded_agent,
    to_session_tool_allowlist,
)


# ============================================================================
# Types
# ============================================================================


class TestTypes:
    def test_block_reply_flush_context(self) -> None:
        ctx: BlockReplyFlushContext = {
            "reason": "message_end",
        }
        assert ctx["reason"] == "message_end"

    def test_embedded_agent_meta(self) -> None:
        meta: EmbeddedAgentMeta = {
            "sessionId": "sess-1",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
        }
        assert meta["sessionId"] == "sess-1"

    def test_embedded_agent_run_meta(self) -> None:
        meta: EmbeddedAgentRunMeta = {
            "durationMs": 1000,
        }
        assert meta["durationMs"] == 1000

    def test_embedded_agent_run_result(self) -> None:
        meta: EmbeddedAgentRunMeta = {
            "durationMs": 1000,
        }
        result: EmbeddedAgentRunResult = {
            "meta": meta,
        }
        assert result["meta"]["durationMs"] == 1000

    def test_embedded_agent_compact_result(self) -> None:
        result: EmbeddedAgentCompactResult = {
            "ok": True,
            "compacted": True,
        }
        assert result["ok"] is True

    def test_embedded_sandbox_info(self) -> None:
        info: EmbeddedSandboxInfo = {
            "enabled": False,
        }
        assert info["enabled"] is False

    def test_embedded_run_failure_signal(self) -> None:
        sig: EmbeddedRunFailureSignal = {
            "kind": "execution_denied",
            "source": "tool",
            "code": "SYSTEM_RUN_DENIED",
            "message": "blocked",
            "fatalForCron": True,
        }
        assert sig["fatalForCron"] is True

    def test_embedded_run_liveness_state(self) -> None:
        state: EmbeddedRunLivenessState = "working"
        assert state == "working"

    def test_full_access_blocked_reason(self) -> None:
        r: EmbeddedFullAccessBlockedReason = "sandbox"
        assert r == "sandbox"

    def test_trace_attempt(self) -> None:
        t: TraceAttempt = {
            "provider": "openai",
            "model": "gpt-4",
            "result": "success",
        }
        assert t["result"] == "success"

    def test_tool_summary_trace(self) -> None:
        t: ToolSummaryTrace = {
            "calls": 3,
            "tools": ["read", "write"],
        }
        assert t["calls"] == 3


# ============================================================================
# Abort detection
# ============================================================================


class TestIsRunnerAbortError:
    def test_none(self) -> None:
        assert is_runner_abort_error(None) is False

    def test_non_object(self) -> None:
        assert is_runner_abort_error("string") is False
        assert is_runner_abort_error(42) is False

    def test_abort_error_named(self) -> None:
        class _AbortError(Exception):
            name = "AbortError"

        assert is_runner_abort_error(_AbortError()) is True

    def test_aborted_message(self) -> None:
        class _Error(Exception):
            message = "operation was aborted"

        assert is_runner_abort_error(_Error()) is True

    def test_unrelated_error(self) -> None:
        class _Error(Exception):
            message = "something else"

        assert is_runner_abort_error(_Error()) is False


# ============================================================================
# Empty assistant turn detection
# ============================================================================


class TestIsZeroUsageEmptyStopAssistantTurn:
    def test_none(self) -> None:
        assert is_zero_usage_empty_stop_assistant_turn(None) is False

    def test_wrong_stop_reason(self) -> None:
        msg = {
            "stopReason": "tool_calls",
            "content": [],
            "usage": {"input": 0, "output": 0},
        }
        assert is_zero_usage_empty_stop_assistant_turn(msg) is False

    def test_non_empty_content(self) -> None:
        msg = {
            "stopReason": "stop",
            "content": [{"type": "text", "text": "hi"}],
            "usage": {"input": 0, "output": 0},
        }
        assert is_zero_usage_empty_stop_assistant_turn(msg) is False

    def test_total_zero_with_components_zero(self) -> None:
        msg = {
            "stopReason": "stop",
            "content": [],
            "usage": {
                "total": 0,
                "input": 0,
                "output": 0,
            },
        }
        assert is_zero_usage_empty_stop_assistant_turn(msg) is True

    def test_components_zero_no_total(self) -> None:
        msg = {
            "stopReason": "stop",
            "content": [],
            "usage": {"input": 0, "output": 0},
        }
        assert is_zero_usage_empty_stop_assistant_turn(msg) is True

    def test_components_nonzero(self) -> None:
        msg = {
            "stopReason": "stop",
            "content": [],
            "usage": {"input": 100, "output": 0},
        }
        assert is_zero_usage_empty_stop_assistant_turn(msg) is False


# ============================================================================
# Failure signal
# ============================================================================


class TestResolveFailureSignalCode:
    def test_valid(self) -> None:
        assert (
            resolve_failure_signal_code("SYSTEM_RUN_DENIED")
            == "SYSTEM_RUN_DENIED"
        )
        assert (
            resolve_failure_signal_code("INVALID_REQUEST")
            == "INVALID_REQUEST"
        )

    def test_invalid(self) -> None:
        assert resolve_failure_signal_code("FOO") is None
        assert resolve_failure_signal_code(None) is None
        assert resolve_failure_signal_code("") is None


class TestResolveEmbeddedRunFailureSignal:
    def test_not_cron(self) -> None:
        result = resolve_embedded_run_failure_signal(
            {"trigger": "user", "lastToolError": {"toolName": "bash"}}
        )
        assert result is None

    def test_cron_bash_denied(self) -> None:
        result = resolve_embedded_run_failure_signal(
            {
                "trigger": "cron",
                "lastToolError": {
                    "toolName": "bash",
                    "errorCode": "SYSTEM_RUN_DENIED",
                    "error": "blocked",
                },
            }
        )
        assert result is not None
        assert result["kind"] == "execution_denied"
        assert result["fatalForCron"] is True

    def test_cron_bash_invalid_request(self) -> None:
        result = resolve_embedded_run_failure_signal(
            {
                "trigger": "cron",
                "lastToolError": {
                    "toolName": "bash",
                    "errorCode": "INVALID_REQUEST",
                },
            }
        )
        assert result is not None
        assert result["code"] == "INVALID_REQUEST"

    def test_cron_non_exec_tool(self) -> None:
        # read is not an exec-like tool.
        result = resolve_embedded_run_failure_signal(
            {
                "trigger": "cron",
                "lastToolError": {
                    "toolName": "read",
                    "errorCode": "SYSTEM_RUN_DENIED",
                },
            }
        )
        assert result is None

    def test_cron_unknown_code(self) -> None:
        result = resolve_embedded_run_failure_signal(
            {
                "trigger": "cron",
                "lastToolError": {
                    "toolName": "bash",
                    "errorCode": "UNKNOWN",
                },
            }
        )
        assert result is None


# ============================================================================
# Session file key
# ============================================================================


class TestResolveEmbeddedSessionFileKey:
    def test_nonexistent(self, tmp_path: pytest.TempPathFactory) -> None:
        # The session file doesn't exist
        # yet — fallback to the parent
        # dir's realpath.
        path = os.path.join(str(tmp_path), "new.jsonl")
        result = resolve_embedded_session_file_key(path)
        assert result.endswith("new.jsonl")

    def test_empty(self) -> None:
        assert resolve_embedded_session_file_key("") == ""


# ============================================================================
# Message action discovery input
# ============================================================================


class TestBuildEmbeddedMessageActionDiscoveryInput:
    def test_basic(self) -> None:
        result = build_embedded_message_action_discovery_input(
            {
                "cfg": {"key": "value"},
                "channel": "telegram",
                "currentChannelId": "123",
                "sessionId": "sess-1",
                "agentId": "default",
                "senderId": "user-1",
                "senderIsOwner": True,
            }
        )
        assert result["channel"] == "telegram"
        assert result["currentChannelId"] == "123"
        assert result["sessionId"] == "sess-1"

    def test_optionals_preserved(self) -> None:
        result = build_embedded_message_action_discovery_input(
            {"channel": "telegram"}
        )
        assert result["currentChannelId"] is None
        assert result["sessionKey"] is None


# ============================================================================
# Execution phase
# ============================================================================


class TestExecutionPhase:
    def test_phases_count(self) -> None:
        # 14 phases per OpenClaw source.
        assert len(EMBEDDED_AGENT_EXECUTION_PHASES) == 14

    def test_first_phase(self) -> None:
        assert EMBEDDED_AGENT_EXECUTION_PHASES[0] == "runner_entered"

    def test_last_phase(self) -> None:
        assert EMBEDDED_AGENT_EXECUTION_PHASES[-1] == "model_call_started"

    def test_labels(self) -> None:
        assert (
            EMBEDDED_AGENT_EXECUTION_PHASE_LABELS["runner_entered"]
            == "runner-entered"
        )

    def test_format(self) -> None:
        assert (
            format_embedded_agent_execution_phase("model_resolution")
            == "model-resolution"
        )
        assert format_embedded_agent_execution_phase(None) is None


# ============================================================================
# Lanes
# ============================================================================


class TestLanes:
    def test_command_lane_constants(self) -> None:
        assert CommandLane.Main == "main"
        assert CommandLane.Cron == "cron"
        assert CommandLane.CronNested == "cron-nested"

    def test_resolve_session_lane_empty(self) -> None:
        assert resolve_session_lane("") == CommandLane.Main

    def test_resolve_session_lane_prefixes(self) -> None:
        assert resolve_session_lane("foo") == "session:foo"
        assert resolve_session_lane("session:bar") == "session:bar"

    def test_resolve_global_lane_none(self) -> None:
        assert resolve_global_lane(None) == CommandLane.Main

    def test_resolve_global_lane_cron(self) -> None:
        assert resolve_global_lane(CommandLane.Cron) == (
            CommandLane.CronNested
        )

    def test_resolve_global_lane_passthrough(self) -> None:
        assert resolve_global_lane("custom") == "custom"

    def test_resolve_embedded_session_lane(self) -> None:
        assert resolve_embedded_session_lane("foo") == "session:foo"


# ============================================================================
# Tool allowlist
# ============================================================================


class TestToolAllowlist:
    def test_reserved_names(self) -> None:
        assert "bash" in AGENT_RESERVED_TOOL_NAMES
        assert "read" in AGENT_RESERVED_TOOL_NAMES
        assert "write" in AGENT_RESERVED_TOOL_NAMES
        assert "edit" in AGENT_RESERVED_TOOL_NAMES
        assert "find" in AGENT_RESERVED_TOOL_NAMES
        assert "grep" in AGENT_RESERVED_TOOL_NAMES
        assert "ls" in AGENT_RESERVED_TOOL_NAMES

    def test_collect_registered(self) -> None:
        class _Tool:
            def __init__(self, name: str) -> None:
                self.name = name

        tools = [_Tool("read"), _Tool("write"), _Tool("read")]
        names = collect_registered_tool_names(tools)
        assert names == {"read", "write"}

    def test_collect_allowed(self) -> None:
        class _Tool:
            def __init__(self, name: str) -> None:
                self.name = name

        class _ClientTool:
            function = {"name": "client-tool"}

        tools = [_Tool("read")]
        client = [_ClientTool()]
        names = collect_allowed_tool_names(tools, client)
        assert "read" in names
        assert "client-tool" in names

    def test_collect_core_with_plugin_filter(self) -> None:
        class _Tool:
            def __init__(self, name: str) -> None:
                self.name = name

        def _is_plugin(tool: Any) -> bool:
            return tool.name == "plugin-x"

        tools = [_Tool("read"), _Tool("plugin-x"), _Tool("write")]
        names = collect_core_builtin_tool_names(tools, _is_plugin)
        assert "read" in names
        assert "write" in names
        assert "plugin-x" not in names

    def test_to_session_allowlist(self) -> None:
        result = to_session_tool_allowlist(
            ["write", "read", "read", "bash"]
        )
        assert result == ["bash", "read", "write"]


# ============================================================================
# Run state
# ============================================================================


class TestRunState:
    def setup_method(self) -> None:
        # Reset the singleton before
        # each test.
        ACTIVE_EMBEDDED_RUNS.clear()
        ACTIVE_EMBEDDED_RUNS_BY_RUN_ID.clear()
        ACTIVE_EMBEDDED_RUN_SNAPSHOTS.clear()
        ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY.clear()
        ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE.clear()
        ABANDONED_EMBEDDED_RUNS_BY_SESSION_ID.clear()
        ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_KEY.clear()
        ABANDONED_EMBEDDED_RUN_SESSION_IDS_BY_FILE.clear()
        RETAINED_EMBEDDED_RUN_ABORTABILITY_RUN_IDS.clear()
        EMBEDDED_RUN_WAITERS.clear()

    def test_empty_get_count(self) -> None:
        assert get_active_embedded_run_count() == 0

    def test_empty_list_keys(self) -> None:
        assert list_active_embedded_run_session_keys() == []

    def test_empty_list_ids(self) -> None:
        assert list_active_embedded_run_session_ids() == []

    def test_resolve_empty_key(self) -> None:
        assert resolve_active_embedded_run_session_id("") is None
        assert resolve_active_embedded_run_session_id("  ") is None

    def test_resolve_unknown_key(self) -> None:
        assert (
            resolve_active_embedded_run_session_id("nonexistent")
            is None
        )

    def test_register_run(self) -> None:
        ACTIVE_EMBEDDED_RUNS["sess-1"] = {"handle": "h"}
        ACTIVE_EMBEDDED_RUNS_BY_RUN_ID["run-1"] = {"handle": "h"}
        ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_KEY["key-1"] = "sess-1"
        ACTIVE_EMBEDDED_RUN_SESSION_IDS_BY_FILE["file-1"] = "sess-1"
        assert get_active_embedded_run_count() == 1
        assert list_active_embedded_run_session_keys() == ["key-1"]
        ids = list_active_embedded_run_session_ids()
        assert "sess-1" in ids
        assert (
            resolve_active_embedded_run_session_id("key-1")
            == "sess-1"
        )


# ============================================================================
# Public entrypoint (stub)
# ============================================================================


class TestRunEmbeddedAgent:
    @pytest.mark.asyncio
    async def test_stub_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            await run_embedded_agent({})


# ============================================================================
# Logger
# ============================================================================


class TestLogger:
    def test_log_is_logger(self) -> None:
        import logging
        assert isinstance(log, logging.Logger)
        assert log.name == "jarvis.agents.embedded_agent_runner"
