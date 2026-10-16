"""Phase 7.6g tests — 16 run/ top-level files (run-attempt-dispatch, run-attempt-result, attempt.queue-message, source-reply-payloads, lane-controller, lane-runtime, terminal-timeout, message-tool-terminal, tool-failure-acknowledgement, message-merge-strategy, tool-media-payloads, tool-activity-heartbeat, pre-persisted-user-turn, agent-end-context, codex-app-server-recovery, compaction-retry-aggregate-timeout)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import pytest

from src.agents.embedded_agent_runner.run.run_attempt_dispatch import (
    dispatch_embedded_run_attempt,
    set_dispatch_embedded_run_attempt_hook,
)
from src.agents.embedded_agent_runner.run.run_attempt_result import (
    build_trace_tool_summary,
    has_completed_model_progress_for_idle_breaker,
    normalize_embedded_run_attempt_result,
    set_build_trace_tool_summary_run_attempt_result_hook,
    set_has_completed_model_progress_for_idle_breaker_hook,
    set_normalize_embedded_run_attempt_result_hook,
)
from src.agents.embedded_agent_runner.run.attempt_queue_message import (
    set_steer_active_session_with_optional_delivery_wait_hook,
    steer_active_session_with_optional_delivery_wait,
)
from src.agents.embedded_agent_runner.run.source_reply_payloads import (
    build_source_reply_payload_state,
    set_build_source_reply_payload_state_hook,
)
from src.agents.embedded_agent_runner.run.lane_controller import (
    create_embedded_run_lane_controller,
    set_create_embedded_run_lane_controller_hook,
)
from src.agents.embedded_agent_runner.run.lane_runtime import (
    EMBEDDED_RUN_LANE_HEARTBEAT_MS,
    EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS,
    resolve_embedded_run_lane_timeout_ms,
    resolve_embedded_run_session_queue_priority,
    set_resolve_embedded_run_lane_timeout_ms_hook,
    set_resolve_embedded_run_session_queue_priority_hook,
    set_with_embedded_run_lane_timeout_hook,
    with_embedded_run_lane_timeout,
)
from src.agents.embedded_agent_runner.run.terminal_timeout import (
    resolve_embedded_run_terminal_timeout,
    set_resolve_embedded_run_terminal_timeout_hook,
)
from src.agents.embedded_agent_runner.run.message_tool_terminal import (
    install_message_tool_only_terminal_hook,
    set_install_message_tool_only_terminal_hook_hook,
)
from src.agents.embedded_agent_runner.run.tool_failure_acknowledgement import (
    has_explicit_mutating_tool_failure_acknowledgement,
)
from src.agents.embedded_agent_runner.run.message_merge_strategy import (
    resolve_message_merge_strategy,
    set_resolve_message_merge_strategy_hook,
)
from src.agents.embedded_agent_runner.run.tool_media_payloads import (
    merge_attempt_tool_media_payloads,
    set_merge_attempt_tool_media_payloads_tool_media_hook,
)
from src.agents.embedded_agent_runner.run.tool_activity_heartbeat import (
    clear_tool_activity_run,
    get_last_tool_activity_ms,
    notify_tool_activity,
    on_tool_activity,
    wrap_embedded_attempt_tool_with_activity,
)
from src.agents.embedded_agent_runner.run.pre_persisted_user_turn import (
    detach_pre_persisted_current_user_turn,
    session_messages_contain_idempotency_key,
    set_detach_pre_persisted_current_user_turn_hook,
    set_session_messages_contain_idempotency_key_hook,
)
from src.agents.embedded_agent_runner.run.agent_end_context import (
    build_embedded_agent_end_context,
    set_build_embedded_agent_end_context_hook,
)
from src.agents.embedded_agent_runner.run.codex_app_server_recovery import (
    has_codex_app_server_recovery_retry_budget,
    resolve_codex_app_server_recovery_retry,
    set_has_codex_app_server_recovery_retry_budget_hook,
    set_resolve_codex_app_server_recovery_retry_hook,
)
from src.agents.embedded_agent_runner.run.compaction_retry_aggregate_timeout import (
    has_active_compaction_retry_work,
    set_has_active_compaction_retry_work_hook,
    set_wait_for_compaction_retry_with_aggregate_timeout_hook,
    wait_for_compaction_retry_with_aggregate_timeout,
)


# ============================================================================
# run-attempt-dispatch
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_run_attempt_dispatch_hooks() -> None:
    set_dispatch_embedded_run_attempt_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_dispatch_embedded_run_attempt_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestDispatchEmbeddedRunAttempt:
    def test_basic(self) -> None:
        result = asyncio.run(
            dispatch_embedded_run_attempt({})
        )
        assert result["outcome"] == "complete"
        assert result["attemptResult"] is None
        assert result["terminal"] is None

    def test_with_hook(self) -> None:
        async def _dispatch(_p: Any) -> Any:
            return {
                "attemptResult": {"runId": "r1"},
                "terminal": {"aborted": True},
                "outcome": "failed",
            }

        set_dispatch_embedded_run_attempt_hook(_dispatch)
        result = asyncio.run(
            dispatch_embedded_run_attempt({})
        )
        assert result["outcome"] == "failed"
        assert result["attemptResult"]["runId"] == "r1"


# ============================================================================
# run-attempt-result
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_run_attempt_result_hooks() -> None:
    set_build_trace_tool_summary_run_attempt_result_hook(lambda _p: {})
    set_has_completed_model_progress_for_idle_breaker_hook(lambda _p: False)
    set_normalize_embedded_run_attempt_result_hook(lambda _p: None)
    yield
    set_build_trace_tool_summary_run_attempt_result_hook(lambda _p: {})
    set_normalize_embedded_run_attempt_result_hook(lambda _p: None)


class TestRunAttemptResult:
    def test_normalize(self) -> None:
        assert normalize_embedded_run_attempt_result({}) is None
        set_normalize_embedded_run_attempt_result_hook(
            lambda _p: "normalized"
        )
        assert normalize_embedded_run_attempt_result({}) == "normalized"

    def test_has_completed_model_progress(self) -> None:
        assert (
            has_completed_model_progress_for_idle_breaker({}) is False
        )
        set_has_completed_model_progress_for_idle_breaker_hook(
            lambda _p: True
        )
        assert (
            has_completed_model_progress_for_idle_breaker({}) is True
        )

    def test_build_trace_tool_summary(self) -> None:
        assert build_trace_tool_summary({}) == {}
        set_build_trace_tool_summary_run_attempt_result_hook(
            lambda _p: {"tools": ["read", "write"]}
        )
        assert build_trace_tool_summary({}) == {"tools": ["read", "write"]}


# ============================================================================
# attempt.queue-message
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_queue_message_hooks() -> None:
    set_steer_active_session_with_optional_delivery_wait_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_steer_active_session_with_optional_delivery_wait_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestSteerActiveSessionWithOptionalDeliveryWait:
    def test_basic(self) -> None:
        result = asyncio.run(
            steer_active_session_with_optional_delivery_wait({})
        )
        assert result["steered"] is True
        assert result["delivered"] is False

    def test_with_hook(self) -> None:
        async def _steer(_p: Any) -> Any:
            return {"steered": True, "delivered": True}

        set_steer_active_session_with_optional_delivery_wait_hook(_steer)
        result = asyncio.run(
            steer_active_session_with_optional_delivery_wait({})
        )
        assert result["delivered"] is True


# ============================================================================
# source-reply-payloads
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_source_reply_hooks() -> None:
    set_build_source_reply_payload_state_hook(lambda _p: {})
    yield
    set_build_source_reply_payload_state_hook(lambda _p: {})


class TestBuildSourceReplyPayloadState:
    def test_basic(self) -> None:
        result = build_source_reply_payload_state({})
        assert result["replyItems"] == []
        assert result["hasSourceReplyPayload"] is False
        assert result["deliveredSourceReplyViaMessageTool"] is False
        assert result["explicitFinalSourceReply"] is None

    def test_with_hook(self) -> None:
        set_build_source_reply_payload_state_hook(
            lambda _p: {
                "replyItems": [{"text": "hi"}],
                "hasSourceReplyPayload": True,
                "deliveredSourceReplyViaMessageTool": True,
                "explicitFinalSourceReply": "final",
            }
        )
        result = build_source_reply_payload_state({})
        assert len(result["replyItems"]) == 1
        assert result["hasSourceReplyPayload"] is True
        assert result["explicitFinalSourceReply"] == "final"


# ============================================================================
# lane-controller
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_lane_controller_hooks() -> None:
    set_create_embedded_run_lane_controller_hook(lambda _p: {})
    yield
    set_create_embedded_run_lane_controller_hook(lambda _p: {})


class TestCreateEmbeddedRunLaneController:
    def test_basic(self) -> None:
        result = create_embedded_run_lane_controller({})
        assert result["lane"] == "main"
        assert result["controller"] is None

    def test_with_hook(self) -> None:
        set_create_embedded_run_lane_controller_hook(
            lambda _p: {"lane": "fast", "controller": "ctrl-1"}
        )
        result = create_embedded_run_lane_controller({})
        assert result["lane"] == "fast"
        assert result["controller"] == "ctrl-1"


# ============================================================================
# lane-runtime
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_lane_runtime_hooks() -> None:
    set_resolve_embedded_run_lane_timeout_ms_hook(
        lambda ms: int(ms) + EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS
    )
    set_resolve_embedded_run_session_queue_priority_hook(lambda _p: 0)
    set_with_embedded_run_lane_timeout_hook(lambda _p: None)
    yield
    set_resolve_embedded_run_lane_timeout_ms_hook(
        lambda ms: int(ms) + EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS
    )
    set_resolve_embedded_run_session_queue_priority_hook(lambda _p: 0)
    set_with_embedded_run_lane_timeout_hook(lambda _p: None)


class TestLaneRuntimeConstants:
    def test_constants(self) -> None:
        assert EMBEDDED_RUN_LANE_TIMEOUT_GRACE_MS == 30_000
        assert EMBEDDED_RUN_LANE_HEARTBEAT_MS == 15_000


class TestLaneRuntime:
    def test_resolve_timeout(self) -> None:
        assert resolve_embedded_run_lane_timeout_ms(0) == 30_000
        assert resolve_embedded_run_lane_timeout_ms(60_000) == 90_000
        set_resolve_embedded_run_lane_timeout_ms_hook(
            lambda _ms: 42_000
        )
        assert resolve_embedded_run_lane_timeout_ms(60_000) == 42_000

    def test_with_timeout(self) -> None:
        assert with_embedded_run_lane_timeout({}) is None
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_with_embedded_run_lane_timeout_hook(_hook)
        with_embedded_run_lane_timeout({"ms": 1000})
        assert captured[0]["ms"] == 1000

    def test_resolve_priority(self) -> None:
        assert resolve_embedded_run_session_queue_priority({}) == 0
        set_resolve_embedded_run_session_queue_priority_hook(
            lambda _p: 5
        )
        assert resolve_embedded_run_session_queue_priority({}) == 5


# ============================================================================
# terminal-timeout
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_terminal_timeout_hooks() -> None:
    set_resolve_embedded_run_terminal_timeout_hook(lambda _p: 0)
    yield
    set_resolve_embedded_run_terminal_timeout_hook(lambda _p: 0)


class TestResolveEmbeddedRunTerminalTimeout:
    def test_basic(self) -> None:
        assert resolve_embedded_run_terminal_timeout({}) == 0
        set_resolve_embedded_run_terminal_timeout_hook(lambda _p: 1000)
        assert resolve_embedded_run_terminal_timeout({}) == 1000


# ============================================================================
# message-tool-terminal
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_message_tool_terminal_hooks() -> None:
    set_install_message_tool_only_terminal_hook_hook(lambda _p: None)
    yield
    set_install_message_tool_only_terminal_hook_hook(lambda _p: None)


class TestInstallMessageToolOnlyTerminalHook:
    def test_basic(self) -> None:
        assert install_message_tool_only_terminal_hook({}) is None
        set_install_message_tool_only_terminal_hook_hook(
            lambda _p: "installed"
        )
        assert install_message_tool_only_terminal_hook({}) == "installed"


# ============================================================================
# tool-failure-acknowledgement
# ============================================================================


class TestHasExplicitMutatingToolFailureAcknowledgement:
    def test_no_text(self) -> None:
        assert (
            has_explicit_mutating_tool_failure_acknowledgement("") is False
        )
        assert (
            has_explicit_mutating_tool_failure_acknowledgement(None)  # type: ignore[arg-type]
            is False
        )

    def test_proceed(self) -> None:
        assert (
            has_explicit_mutating_tool_failure_acknowledgement(
                "proceed with the edit"
            )
            is True
        )
        assert (
            has_explicit_mutating_tool_failure_acknowledgement(
                "Continue with that change"
            )
            is True
        )
        assert (
            has_explicit_mutating_tool_failure_acknowledgement(
                "Proceed after the tool failure"
            )
            is True
        )

    def test_no_match(self) -> None:
        assert (
            has_explicit_mutating_tool_failure_acknowledgement(
                "what is the weather"
            )
            is False
        )
        assert (
            has_explicit_mutating_tool_failure_acknowledgement(
                "tell me a joke"
            )
            is False
        )


# ============================================================================
# message-merge-strategy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_message_merge_strategy_hooks() -> None:
    set_resolve_message_merge_strategy_hook(lambda: {})
    yield
    set_resolve_message_merge_strategy_hook(lambda: {})


class TestResolveMessageMergeStrategy:
    def test_basic(self) -> None:
        assert resolve_message_merge_strategy() == {}

    def test_with_hook(self) -> None:
        set_resolve_message_merge_strategy_hook(
            lambda: {"strategy": "merge", "rules": []}
        )
        assert resolve_message_merge_strategy() == {
            "strategy": "merge",
            "rules": [],
        }


# ============================================================================
# tool-media-payloads
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_media_payloads_hooks() -> None:
    set_merge_attempt_tool_media_payloads_tool_media_hook(lambda _p: [])
    yield
    set_merge_attempt_tool_media_payloads_tool_media_hook(lambda _p: [])


class TestMergeAttemptToolMediaPayloads:
    def test_basic(self) -> None:
        assert merge_attempt_tool_media_payloads({}) == []

    def test_with_hook(self) -> None:
        set_merge_attempt_tool_media_payloads_tool_media_hook(
            lambda _p: [{"media": "url"}]
        )
        assert merge_attempt_tool_media_payloads({}) == [{"media": "url"}]


# ============================================================================
# tool-activity-heartbeat
# ============================================================================


class TestToolActivityHeartbeat:
    def test_get_set(self) -> None:
        assert get_last_tool_activity_ms(None) is None
        assert get_last_tool_activity_ms("") is None
        clear_tool_activity_run("r1")
        assert get_last_tool_activity_ms("r1") is None
        notify_tool_activity("r1")
        last = get_last_tool_activity_ms("r1")
        assert isinstance(last, int)
        assert last > 0

    def test_clear(self) -> None:
        notify_tool_activity("r1")
        assert get_last_tool_activity_ms("r1") is not None
        clear_tool_activity_run("r1")
        assert get_last_tool_activity_ms("r1") is None

    def test_on_tool_activity(self) -> None:
        called = {"n": 0}

        def _cb() -> None:
            called["n"] += 1

        on_tool_activity("r1", _cb)
        assert called["n"] == 1
        # Should also have updated the timestamp.
        assert get_last_tool_activity_ms("r1") is not None

    def test_wrap_tool(self) -> None:
        tool = {"name": "read", "runId": "r1"}
        wrapped = wrap_embedded_attempt_tool_with_activity(tool)
        assert wrapped["wrapped"] is True
        assert wrapped["toolName"] == "read"
        # Call the activity callback to ensure it doesn't raise.
        wrapped["activityCallback"]()
        assert get_last_tool_activity_ms("r1") is not None

    def test_wrap_non_dict(self) -> None:
        assert wrap_embedded_attempt_tool_with_activity("not a dict") == "not a dict"  # type: ignore[arg-type]


# ============================================================================
# pre-persisted-user-turn
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_pre_persisted_user_turn_hooks() -> None:
    set_detach_pre_persisted_current_user_turn_hook(lambda _p: None)
    set_session_messages_contain_idempotency_key_hook(lambda _p: False)
    yield
    set_detach_pre_persisted_current_user_turn_hook(lambda _p: None)
    set_session_messages_contain_idempotency_key_hook(lambda _p: False)


class TestPrePersistedUserTurn:
    def test_contains_idempotency_key(self) -> None:
        assert session_messages_contain_idempotency_key({}) is False
        set_session_messages_contain_idempotency_key_hook(
            lambda _p: True
        )
        assert session_messages_contain_idempotency_key({}) is True

    def test_detach(self) -> None:
        assert detach_pre_persisted_current_user_turn({}) is None
        set_detach_pre_persisted_current_user_turn_hook(
            lambda _p: "detached"
        )
        assert detach_pre_persisted_current_user_turn({}) == "detached"


# ============================================================================
# agent-end-context
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_agent_end_context_hooks() -> None:
    set_build_embedded_agent_end_context_hook(lambda _p: {})
    yield
    set_build_embedded_agent_end_context_hook(lambda _p: {})


class TestBuildEmbeddedAgentEndContext:
    def test_basic(self) -> None:
        result = build_embedded_agent_end_context({})
        assert result["ended"] is True
        assert result["summary"] is None

    def test_with_hook(self) -> None:
        set_build_embedded_agent_end_context_hook(
            lambda _p: {"ended": True, "summary": "done"}
        )
        result = build_embedded_agent_end_context({})
        assert result["summary"] == "done"


# ============================================================================
# codex-app-server-recovery
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_codex_app_server_recovery_hooks() -> None:
    set_has_codex_app_server_recovery_retry_budget_hook(lambda _p: False)
    set_resolve_codex_app_server_recovery_retry_hook(lambda _p: None)
    yield
    set_has_codex_app_server_recovery_retry_budget_hook(lambda _p: False)
    set_resolve_codex_app_server_recovery_retry_hook(lambda _p: None)


class TestCodexAppServerRecovery:
    def test_has_budget(self) -> None:
        assert has_codex_app_server_recovery_retry_budget({}) is False
        set_has_codex_app_server_recovery_retry_budget_hook(
            lambda _p: True
        )
        assert has_codex_app_server_recovery_retry_budget({}) is True

    def test_resolve_retry(self) -> None:
        assert resolve_codex_app_server_recovery_retry({}) is None
        set_resolve_codex_app_server_recovery_retry_hook(
            lambda _p: {"retry": True}
        )
        assert resolve_codex_app_server_recovery_retry({}) == {"retry": True}


# ============================================================================
# compaction-retry-aggregate-timeout
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_compaction_retry_aggregate_timeout_hooks() -> None:
    set_has_active_compaction_retry_work_hook(lambda _p: False)
    set_wait_for_compaction_retry_with_aggregate_timeout_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_has_active_compaction_retry_work_hook(lambda _p: False)
    set_wait_for_compaction_retry_with_aggregate_timeout_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestCompactionRetryAggregateTimeout:
    def test_has_active(self) -> None:
        assert has_active_compaction_retry_work({}) is False
        set_has_active_compaction_retry_work_hook(lambda _p: True)
        assert has_active_compaction_retry_work({}) is True

    def test_wait(self) -> None:
        result = asyncio.run(
            wait_for_compaction_retry_with_aggregate_timeout({})
        )
        assert result["completed"] is False
        assert result["timedOut"] is False

    def test_wait_with_hook(self) -> None:
        async def _wait(_p: Any) -> Any:
            return {"completed": True, "timedOut": False}

        set_wait_for_compaction_retry_with_aggregate_timeout_hook(_wait)
        result = asyncio.run(
            wait_for_compaction_retry_with_aggregate_timeout({})
        )
        assert result["completed"] is True
