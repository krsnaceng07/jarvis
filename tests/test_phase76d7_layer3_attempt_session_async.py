"""Phase 7.6d-7 tests — 12 attempt.* files (async-tasks, sessions-yield, context-engine-helpers, bootstrap-prepare, transcript-helpers, stop-reason-recovery, subscription-cleanup, session-manager-prepare, session-runtime-prepare, setup, thread-helpers, run-decisions)."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.agents.embedded_agent_runner.run.attempt_async_tasks import (
    requires_completion_required_async_task_wait,
    set_requires_completion_required_async_task_wait_hook,
    set_should_wait_for_completion_required_async_tasks_hook,
    set_wait_for_completion_required_async_tasks_hook,
    should_wait_for_completion_required_async_tasks,
    wait_for_completion_required_async_tasks,
)
from src.agents.embedded_agent_runner.run.attempt_sessions_yield import (
    SESSIONS_YIELD_ABORT_REASON,
    create_yield_aborted_response,
    is_sessions_yield_abort_error,
    is_sessions_yield_abort_reason,
    persist_sessions_yield_context_message,
    queue_sessions_yield_interrupt_message,
    set_create_yield_aborted_response_hook,
    set_persist_sessions_yield_context_message_hook,
    set_queue_sessions_yield_interrupt_message_hook,
    set_strip_sessions_yield_artifacts_hook,
    set_wait_for_sessions_yield_abort_settle_hook,
    strip_sessions_yield_artifacts,
    wait_for_sessions_yield_abort_settle,
)
from src.agents.embedded_agent_runner.run.attempt_context_engine_helpers import (
    build_context_engine_prompt_cache_info,
    build_loop_prompt_cache_info,
    find_current_attempt_assistant_message,
    resolve_attempt_bootstrap_context,
    resolve_prompt_cache_touch_timestamp,
    set_build_context_engine_prompt_cache_info_hook,
    set_build_loop_prompt_cache_info_hook,
    set_find_current_attempt_assistant_message_hook,
    set_resolve_attempt_bootstrap_context_hook,
    set_resolve_prompt_cache_touch_timestamp_hook,
)
from src.agents.embedded_agent_runner.run.attempt_bootstrap_prepare import (
    prepare_embedded_attempt_bootstrap,
    set_prepare_bootstrap_hook,
)
from src.agents.embedded_agent_runner.run.attempt_transcript_helpers import (
    flush_session_manager_transcript,
    load_attempt_session_entry_after_quota_maintenance,
    normalize_compaction_recovery_transcript_tail,
    remove_trailing_mid_turn_precheck_assistant_error,
    repair_attempt_tool_use_result_pairing,
    resolve_attempt_trajectory_session_file,
    resolve_existing_attempt_transcript_state,
    set_flush_session_manager_transcript_hook,
    set_load_attempt_session_entry_after_quota_maintenance_hook,
    set_normalize_compaction_recovery_transcript_tail_hook,
    set_remove_trailing_mid_turn_precheck_assistant_error_hook,
    set_repair_attempt_tool_use_result_pairing_hook,
    set_resolve_attempt_trajectory_session_file_hook,
    set_resolve_existing_attempt_transcript_state_hook,
)
from src.agents.embedded_agent_runner.run.attempt_stop_reason_recovery import (
    set_wrap_stream_fn_handle_sensitive_stop_reason_hook,
    wrap_stream_fn_handle_sensitive_stop_reason,
)
from src.agents.embedded_agent_runner.run.attempt_subscription_cleanup import (
    build_embedded_subscription_params,
    cleanup_embedded_attempt_resources,
    set_build_embedded_subscription_params_hook,
    set_cleanup_embedded_attempt_resources_hook,
)
from src.agents.embedded_agent_runner.run.attempt_session_manager_prepare import (
    prepare_embedded_attempt_session_manager,
    set_prepare_session_manager_hook,
)
from src.agents.embedded_agent_runner.run.attempt_session_runtime_prepare import (
    prepare_embedded_attempt_session_runtime,
    set_prepare_session_runtime_hook,
)
from src.agents.embedded_agent_runner.run.attempt_setup import (
    prepare_embedded_attempt_setup,
    set_prepare_setup_hook,
)
from src.agents.embedded_agent_runner.run.attempt_thread_helpers import (
    append_attempt_cache_ttl_if_needed,
    compose_system_prompt_with_hook_context,
    resolve_attempt_spawn_workspace_dir,
    set_append_attempt_cache_ttl_if_needed_hook,
    set_compose_system_prompt_with_hook_context_hook,
    set_resolve_attempt_spawn_workspace_dir_hook,
    set_should_persist_completed_bootstrap_turn_hook,
    should_persist_completed_bootstrap_turn,
)
from src.agents.embedded_agent_runner.run.attempt_run_decisions import (
    resolve_attempt_stream_auth_profile_id,
    resolve_attempt_tool_policy_message_provider,
    resolve_embedded_attempt_session_write_lock_options,
    resolve_unknown_tool_guard_threshold,
    set_resolve_attempt_stream_auth_profile_id_hook,
    set_resolve_attempt_tool_policy_message_provider_hook,
    set_resolve_embedded_attempt_session_write_lock_options_hook,
    set_resolve_unknown_tool_guard_threshold_hook,
    set_should_run_llm_output_hooks_for_attempt_run_decisions_hook,
    should_run_llm_output_hooks_for_attempt,
)


# ============================================================================
# attempt.async-tasks
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_async_tasks_hooks() -> None:
    set_requires_completion_required_async_task_wait_hook(lambda _p: False)
    set_should_wait_for_completion_required_async_tasks_hook(lambda _p: False)
    set_wait_for_completion_required_async_tasks_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_requires_completion_required_async_task_wait_hook(lambda _p: False)
    set_should_wait_for_completion_required_async_tasks_hook(lambda _p: False)
    set_wait_for_completion_required_async_tasks_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestAttemptAsyncTasks:
    def test_requires(self) -> None:
        assert requires_completion_required_async_task_wait({}) is False
        set_requires_completion_required_async_task_wait_hook(
            lambda _p: True
        )
        assert requires_completion_required_async_task_wait({}) is True

    def test_should_wait(self) -> None:
        assert should_wait_for_completion_required_async_tasks({}) is False
        set_should_wait_for_completion_required_async_tasks_hook(
            lambda _p: True
        )
        assert should_wait_for_completion_required_async_tasks({}) is True

    def test_wait(self) -> None:
        result = asyncio.run(
            wait_for_completion_required_async_tasks({})
        )
        assert result["waited"] is True
        assert result["completed"] == []
        assert result["remaining"] == []

    def test_wait_with_hook(self) -> None:
        async def _wait(_p: Any) -> Any:
            return {
                "waited": False,
                "completed": [{"id": "1"}],
                "remaining": [{"id": "2"}],
            }

        set_wait_for_completion_required_async_tasks_hook(_wait)
        result = asyncio.run(
            wait_for_completion_required_async_tasks({})
        )
        assert result["waited"] is False
        assert len(result["completed"]) == 1


# ============================================================================
# attempt.sessions-yield
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_sessions_yield_hooks() -> None:
    set_create_yield_aborted_response_hook(
        lambda p: {"aborted": True, "reason": dict(SESSIONS_YIELD_ABORT_REASON)}
    )
    set_persist_sessions_yield_context_message_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_queue_sessions_yield_interrupt_message_hook(lambda _p: None)
    set_strip_sessions_yield_artifacts_hook(lambda _p: None)
    set_wait_for_sessions_yield_abort_settle_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_create_yield_aborted_response_hook(
        lambda p: {"aborted": True, "reason": dict(SESSIONS_YIELD_ABORT_REASON)}
    )
    set_persist_sessions_yield_context_message_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_queue_sessions_yield_interrupt_message_hook(lambda _p: None)
    set_strip_sessions_yield_artifacts_hook(lambda _p: None)
    set_wait_for_sessions_yield_abort_settle_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestAttemptSessionsYield:
    def test_reason(self) -> None:
        assert SESSIONS_YIELD_ABORT_REASON["code"] == "sessions_yield"
        assert SESSIONS_YIELD_ABORT_REASON["turnHandoff"] is True

    def test_create_yield_aborted(self) -> None:
        result = create_yield_aborted_response({})
        assert result["aborted"] is True
        assert result["reason"]["code"] == "sessions_yield"

    def test_is_sessions_yield_abort_error(self) -> None:
        assert is_sessions_yield_abort_error({}) is False
        assert (
            is_sessions_yield_abort_error({"reason": {"code": "sessions_yield"}})
            is True
        )
        assert (
            is_sessions_yield_abort_error({"code": "sessions_yield"})
            is True
        )
        assert is_sessions_yield_abort_error("not a dict") is False
        assert is_sessions_yield_abort_error(None) is False

    def test_is_sessions_yield_abort_reason(self) -> None:
        assert is_sessions_yield_abort_reason({}) is False
        assert is_sessions_yield_abort_reason({"code": "sessions_yield"}) is True
        assert is_sessions_yield_abort_reason("sessions_yield") is True
        assert is_sessions_yield_abort_reason("other") is False

    def test_queue_interrupt(self) -> None:
        result = queue_sessions_yield_interrupt_message({})
        assert result is None

    def test_persist_context(self) -> None:
        result = asyncio.run(
            persist_sessions_yield_context_message({})
        )
        assert result is None

    def test_strip(self) -> None:
        strip_sessions_yield_artifacts({})

    def test_wait(self) -> None:
        result = asyncio.run(
            wait_for_sessions_yield_abort_settle({})
        )
        assert result["settled"] is True
        assert result["sessionId"] is None


# ============================================================================
# attempt.context-engine-helpers
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_context_engine_helpers_hooks() -> None:
    set_build_context_engine_prompt_cache_info_hook(lambda _p: {})
    set_build_loop_prompt_cache_info_hook(lambda _p: {})
    set_find_current_attempt_assistant_message_hook(lambda _p: None)
    set_resolve_attempt_bootstrap_context_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_resolve_prompt_cache_touch_timestamp_hook(lambda _p: 0)
    yield
    set_build_context_engine_prompt_cache_info_hook(lambda _p: {})
    set_build_loop_prompt_cache_info_hook(lambda _p: {})
    set_find_current_attempt_assistant_message_hook(lambda _p: None)
    set_resolve_attempt_bootstrap_context_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_resolve_prompt_cache_touch_timestamp_hook(lambda _p: 0)


class TestContextEngineHelpers:
    def test_resolve_bootstrap(self) -> None:
        result = asyncio.run(
            resolve_attempt_bootstrap_context({})
        )
        assert result is None

    def test_build_prompt_cache_info(self) -> None:
        assert build_context_engine_prompt_cache_info({}) == {}

    def test_find_assistant_message(self) -> None:
        assert find_current_attempt_assistant_message({}) is None

    def test_resolve_touch_timestamp(self) -> None:
        assert resolve_prompt_cache_touch_timestamp({}) == 0

    def test_build_loop_prompt_cache_info(self) -> None:
        assert build_loop_prompt_cache_info({}) == {}


# ============================================================================
# attempt-bootstrap-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_bootstrap_prepare_hooks() -> None:
    set_prepare_bootstrap_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_bootstrap_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptBootstrap:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_bootstrap({})
        )
        assert result["bootstrapFiles"] == []
        assert result["bootstrapPromptWarning"] is None
        assert result["shouldRecordCompletedBootstrapTurn"] is False

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "bootstrapFiles": [{"path": "/etc/foo"}],
                "bootstrapPromptWarning": {"signature": "x"},
                "shouldRecordCompletedBootstrapTurn": True,
            }

        set_prepare_bootstrap_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_bootstrap({})
        )
        assert len(result["bootstrapFiles"]) == 1
        assert result["shouldRecordCompletedBootstrapTurn"] is True


# ============================================================================
# attempt-transcript-helpers
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_transcript_helpers_hooks() -> None:
    set_flush_session_manager_transcript_hook(lambda _p: None)
    set_load_attempt_session_entry_after_quota_maintenance_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_normalize_compaction_recovery_transcript_tail_hook(lambda _p: None)
    set_remove_trailing_mid_turn_precheck_assistant_error_hook(lambda _p: None)
    set_repair_attempt_tool_use_result_pairing_hook(lambda _p: None)
    set_resolve_attempt_trajectory_session_file_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_resolve_existing_attempt_transcript_state_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_flush_session_manager_transcript_hook(lambda _p: None)
    set_repair_attempt_tool_use_result_pairing_hook(lambda _p: None)


class TestAttemptTranscriptHelpers:
    def test_flush(self) -> None:
        flush_session_manager_transcript({})  # no-op default

    def test_repair_pairing(self) -> None:
        assert repair_attempt_tool_use_result_pairing({}) is None

    def test_remove_trailing(self) -> None:
        assert (
            remove_trailing_mid_turn_precheck_assistant_error({}) is None
        )

    def test_normalize_compaction_recovery(self) -> None:
        assert (
            normalize_compaction_recovery_transcript_tail({}) is None
        )

    def test_load_session_entry(self) -> None:
        result = asyncio.run(
            load_attempt_session_entry_after_quota_maintenance({})
        )
        assert result is None

    def test_resolve_trajectory_session_file(self) -> None:
        result = asyncio.run(
            resolve_attempt_trajectory_session_file({})
        )
        assert result is None

    def test_resolve_existing_transcript_state(self) -> None:
        result = asyncio.run(
            resolve_existing_attempt_transcript_state({})
        )
        assert result is None


# ============================================================================
# attempt.stop-reason-recovery
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stop_reason_hooks() -> None:
    set_wrap_stream_fn_handle_sensitive_stop_reason_hook(
        lambda p: p.get("baseFn")
    )
    yield
    set_wrap_stream_fn_handle_sensitive_stop_reason_hook(
        lambda p: p.get("baseFn")
    )


class TestWrapStreamFnHandleSensitiveStopReason:
    def test_basic(self) -> None:
        base = "stream-fn-1"
        result = wrap_stream_fn_handle_sensitive_stop_reason(base)
        assert result == "stream-fn-1"

    def test_with_hook(self) -> None:
        set_wrap_stream_fn_handle_sensitive_stop_reason_hook(
            lambda _p: "wrapped"
        )
        assert (
            wrap_stream_fn_handle_sensitive_stop_reason("base") == "wrapped"
        )


# ============================================================================
# attempt.subscription-cleanup
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_subscription_cleanup_hooks() -> None:
    set_build_embedded_subscription_params_hook(lambda _p: {})
    set_cleanup_embedded_attempt_resources_hook(
        lambda _p: asyncio.sleep(0)
    )
    yield
    set_build_embedded_subscription_params_hook(lambda _p: {})
    set_cleanup_embedded_attempt_resources_hook(
        lambda _p: asyncio.sleep(0)
    )


class TestBuildEmbeddedSubscriptionParams:
    def test_basic(self) -> None:
        result = build_embedded_subscription_params({})
        assert result["stream"] == {}
        assert result["hooks"] == {}
        assert result["diagnostic"] == {}

    def test_with_hook(self) -> None:
        set_build_embedded_subscription_params_hook(
            lambda _p: {
                "stream": "stream-1",
                "hooks": {"onX": lambda: None},
            }
        )
        result = build_embedded_subscription_params({})
        assert result["stream"] == "stream-1"
        assert "onX" in result["hooks"]


class TestCleanupEmbeddedAttemptResources:
    def test_basic(self) -> None:
        result = asyncio.run(
            cleanup_embedded_attempt_resources({})
        )
        assert result["cleanedUp"] is True
        assert result["unsubscribed"] is False

    def test_with_hook(self) -> None:
        async def _cleanup(_p: Any) -> Any:
            return {"cleanedUp": True, "unsubscribed": True}

        set_cleanup_embedded_attempt_resources_hook(_cleanup)
        result = asyncio.run(
            cleanup_embedded_attempt_resources({})
        )
        assert result["unsubscribed"] is True


# ============================================================================
# attempt-session-manager-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_manager_prepare_hooks() -> None:
    set_prepare_session_manager_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_session_manager_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptSessionManager:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_session_manager({})
        )
        assert result["sessionManager"] is None
        assert result["sessionState"] == {}

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "sessionManager": "sm",
                "sessionState": {"key": "value"},
                "sessionFile": "/tmp/s.jsonl",
            }

        set_prepare_session_manager_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_session_manager({})
        )
        assert result["sessionManager"] == "sm"
        assert result["sessionFile"] == "/tmp/s.jsonl"


# ============================================================================
# attempt-session-runtime-prepare
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_runtime_prepare_hooks() -> None:
    set_prepare_session_runtime_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_session_runtime_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptSessionRuntime:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_session_runtime({})
        )
        assert result["sessionRuntime"] == {}
        assert result["state"] == {}

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "sessionRuntime": {"sessionId": "s1"},
                "state": {"promptCache": True},
                "sessionPromptState": {"sent": 1},
                "trajectoryRecorder": "tr",
            }

        set_prepare_session_runtime_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_session_runtime({})
        )
        assert result["sessionRuntime"]["sessionId"] == "s1"
        assert result["trajectoryRecorder"] == "tr"


# ============================================================================
# attempt-setup
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_setup_hooks() -> None:
    set_prepare_setup_hook(lambda _p: asyncio.sleep(0))
    yield
    set_prepare_setup_hook(lambda _p: asyncio.sleep(0))


class TestPrepareEmbeddedAttemptSetup:
    def test_basic(self) -> None:
        result = asyncio.run(
            prepare_embedded_attempt_setup({})
        )
        assert result["sessionAgentId"] is None
        assert result["effectiveFsWorkspaceOnly"] is False

    def test_with_hook(self) -> None:
        async def _prepare(_p: Any) -> Any:
            return {
                "sessionAgentId": "a1",
                "effectiveWorkspace": "/tmp/ws",
                "effectiveFsWorkspaceOnly": True,
                "sandbox": {"type": "docker"},
            }

        set_prepare_setup_hook(_prepare)
        result = asyncio.run(
            prepare_embedded_attempt_setup({})
        )
        assert result["sessionAgentId"] == "a1"
        assert result["effectiveFsWorkspaceOnly"] is True
        assert result["sandbox"]["type"] == "docker"


# ============================================================================
# attempt.thread-helpers
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_thread_helpers_hooks() -> None:
    set_append_attempt_cache_ttl_if_needed_hook(lambda _p: None)
    set_compose_system_prompt_with_hook_context_hook(lambda _p: None)
    set_resolve_attempt_spawn_workspace_dir_hook(lambda _p: None)
    set_should_persist_completed_bootstrap_turn_hook(lambda _p: False)
    yield
    set_append_attempt_cache_ttl_if_needed_hook(lambda _p: None)
    set_compose_system_prompt_with_hook_context_hook(lambda _p: None)
    set_resolve_attempt_spawn_workspace_dir_hook(lambda _p: None)
    set_should_persist_completed_bootstrap_turn_hook(lambda _p: False)


class TestAttemptThreadHelpers:
    def test_compose_system_prompt(self) -> None:
        assert compose_system_prompt_with_hook_context({}) is None
        set_compose_system_prompt_with_hook_context_hook(
            lambda _p: "sp-with-ctx"
        )
        assert (
            compose_system_prompt_with_hook_context({}) == "sp-with-ctx"
        )

    def test_resolve_spawn_workspace_dir(self) -> None:
        assert resolve_attempt_spawn_workspace_dir({}) is None
        set_resolve_attempt_spawn_workspace_dir_hook(
            lambda _p: "/tmp/spawn"
        )
        assert (
            resolve_attempt_spawn_workspace_dir({}) == "/tmp/spawn"
        )

    def test_append_cache_ttl(self) -> None:
        assert append_attempt_cache_ttl_if_needed({}) is None

    def test_should_persist(self) -> None:
        assert should_persist_completed_bootstrap_turn({}) is False
        set_should_persist_completed_bootstrap_turn_hook(
            lambda _p: True
        )
        assert should_persist_completed_bootstrap_turn({}) is True


# ============================================================================
# attempt.run-decisions
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_run_decisions_hooks() -> None:
    set_resolve_attempt_stream_auth_profile_id_hook(lambda _p: None)
    set_resolve_attempt_tool_policy_message_provider_hook(lambda _p: None)
    set_resolve_embedded_attempt_session_write_lock_options_hook(
        lambda _p: {}
    )
    set_resolve_unknown_tool_guard_threshold_hook(lambda _p: 0)
    set_should_run_llm_output_hooks_for_attempt_run_decisions_hook(
        lambda _p: False
    )
    yield
    set_resolve_attempt_stream_auth_profile_id_hook(lambda _p: None)
    set_resolve_attempt_tool_policy_message_provider_hook(lambda _p: None)
    set_resolve_embedded_attempt_session_write_lock_options_hook(
        lambda _p: {}
    )
    set_resolve_unknown_tool_guard_threshold_hook(lambda _p: 0)
    set_should_run_llm_output_hooks_for_attempt_run_decisions_hook(
        lambda _p: False
    )


class TestAttemptRunDecisions:
    def test_session_write_lock(self) -> None:
        assert (
            resolve_embedded_attempt_session_write_lock_options({}) == {}
        )

    def test_stream_auth_profile_id(self) -> None:
        assert resolve_attempt_stream_auth_profile_id({}) is None
        set_resolve_attempt_stream_auth_profile_id_hook(
            lambda _p: "ap-1"
        )
        assert resolve_attempt_stream_auth_profile_id({}) == "ap-1"

    def test_unknown_tool_guard_threshold(self) -> None:
        assert resolve_unknown_tool_guard_threshold() == 0
        assert resolve_unknown_tool_guard_threshold({"a": 1}) == 0
        set_resolve_unknown_tool_guard_threshold_hook(lambda _p: 5)
        assert resolve_unknown_tool_guard_threshold({"a": 1}) == 5

    def test_should_run_llm_output(self) -> None:
        assert should_run_llm_output_hooks_for_attempt({}) is False
        set_should_run_llm_output_hooks_for_attempt_run_decisions_hook(
            lambda _p: True
        )
        assert should_run_llm_output_hooks_for_attempt({}) is True

    def test_tool_policy_message_provider(self) -> None:
        assert resolve_attempt_tool_policy_message_provider({}) is None
