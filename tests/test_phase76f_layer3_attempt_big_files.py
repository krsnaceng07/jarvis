"""Phase 7.6f tests — 6 BIG attempt.* files (session-lock, tool-call-normalization, tool-call-argument-repair, llm-boundary, prompt-helpers, model-diagnostic-events)."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.attempt_session_lock import (
    EmbeddedAttemptSessionTakeoverError,
    MAX_BENIGN_SESSION_FENCE_ADVANCE_BYTES,
    MAX_BENIGN_SESSION_FENCE_CONTENT_DIGEST_BYTES,
    MAX_BENIGN_SESSION_FENCE_REWRITE_BYTES,
    MAX_BENIGN_SESSION_FENCE_REWRITE_RESULT_BYTES,
    MAX_SAFE_FILE_OFFSET,
    acquire_embedded_attempt_session_file_owner,
    create_embedded_attempt_session_lock_controller,
    install_prompt_submission_lock_release,
    set_acquire_embedded_attempt_session_file_owner_hook,
    set_create_embedded_attempt_session_lock_controller_hook,
    set_install_prompt_submission_lock_release_hook,
)
from src.agents.embedded_agent_runner.run.attempt_tool_call_normalization import (
    sanitize_openai_responses_replay_for_stream,
    sanitize_replay_tool_call_ids_for_stream,
    set_sanitize_openai_responses_replay_for_stream_hook,
    set_sanitize_replay_tool_call_ids_for_stream_hook,
    set_should_apply_replay_tool_call_id_sanitizer_hook,
    set_wrap_stream_fn_promote_standalone_text_tool_calls_hook,
    set_wrap_stream_fn_sanitize_malformed_tool_calls_hook,
    set_wrap_stream_fn_trim_tool_call_names_hook,
    should_apply_replay_tool_call_id_sanitizer,
    wrap_stream_fn_promote_standalone_text_tool_calls,
    wrap_stream_fn_sanitize_malformed_tool_calls,
    wrap_stream_fn_trim_tool_call_names,
)
from src.agents.embedded_agent_runner.run.attempt_tool_call_argument_repair import (
    set_should_repair_malformed_tool_call_arguments_hook,
    set_wrap_stream_fn_decode_xai_tool_call_arguments_hook,
    set_wrap_stream_fn_repair_malformed_tool_call_arguments_hook,
    should_repair_malformed_tool_call_arguments,
    wrap_stream_fn_decode_xai_tool_call_arguments,
    wrap_stream_fn_repair_malformed_tool_call_arguments,
)
from src.agents.embedded_agent_runner.run.attempt_llm_boundary import (
    install_model_prompt_transform,
    install_runtime_context_message_for_prompt,
    normalize_current_prompt_text_for_llm_boundary,
    normalize_messages_for_current_prompt_boundary,
    normalize_messages_for_llm_boundary,
    set_install_model_prompt_transform_hook,
    set_install_runtime_context_message_for_prompt_hook,
    set_normalize_current_prompt_text_for_llm_boundary_hook,
    set_normalize_messages_for_current_prompt_boundary_hook,
    set_normalize_messages_for_llm_boundary_hook,
)
from src.agents.embedded_agent_runner.run.attempt_prompt_helpers import (
    build_after_turn_runtime_context,
    build_after_turn_runtime_context_from_usage,
    forget_prompt_build_drain_cache_for_run,
    merge_orphaned_trailing_user_prompt,
    prepend_system_prompt_addition,
    resolve_attempt_fs_workspace_only,
    resolve_attempt_media_task_system_prompt_addition,
    resolve_prompt_build_hook_result,
    resolve_prompt_mode_for_session,
    set_build_after_turn_runtime_context_from_usage_hook,
    set_build_after_turn_runtime_context_hook,
    set_forget_prompt_build_drain_cache_for_run_hook,
    set_merge_orphaned_trailing_user_prompt_hook,
    set_prepend_system_prompt_addition_hook,
    set_resolve_attempt_fs_workspace_only_hook,
    set_resolve_attempt_media_task_system_prompt_addition_hook,
    set_resolve_prompt_build_hook_result_hook,
    set_resolve_prompt_mode_for_session_hook,
    set_should_inject_heartbeat_prompt_hook,
    set_should_warn_on_orphaned_user_repair_hook,
    should_inject_heartbeat_prompt,
    should_warn_on_orphaned_user_repair,
)
from src.agents.embedded_agent_runner.run.attempt_model_diagnostic_events import (
    set_wrap_stream_fn_with_diagnostic_model_call_events_hook,
    wrap_stream_fn_with_diagnostic_model_call_events,
)


# ============================================================================
# attempt.session-lock
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_lock_hooks() -> None:
    set_acquire_embedded_attempt_session_file_owner_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_create_embedded_attempt_session_lock_controller_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_install_prompt_submission_lock_release_hook(lambda _p: None)
    yield
    set_acquire_embedded_attempt_session_file_owner_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_create_embedded_attempt_session_lock_controller_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_install_prompt_submission_lock_release_hook(lambda _p: None)


class TestSessionLockConstants:
    def test_constants(self) -> None:
        assert MAX_BENIGN_SESSION_FENCE_ADVANCE_BYTES == 1024 * 1024
        assert MAX_BENIGN_SESSION_FENCE_REWRITE_BYTES == 8 * 1024 * 1024
        assert (
            MAX_BENIGN_SESSION_FENCE_REWRITE_RESULT_BYTES
            == 8 * 1024 * 1024
        )
        assert (
            MAX_BENIGN_SESSION_FENCE_CONTENT_DIGEST_BYTES
            == 32 * 1024 * 1024
        )
        assert MAX_SAFE_FILE_OFFSET == 2**53 - 1


class TestSessionTakeoverError:
    def test_basic(self) -> None:
        err = EmbeddedAttemptSessionTakeoverError("oops")
        assert str(err) == "oops"
        assert err.takeover == {}

    def test_with_takeover(self) -> None:
        err = EmbeddedAttemptSessionTakeoverError(
            "conflict", {"reason": "stale"}
        )
        assert err.takeover == {"reason": "stale"}


class TestAcquireEmbeddedAttemptSessionFileOwner:
    def test_basic(self) -> None:
        result = asyncio.run(
            acquire_embedded_attempt_session_file_owner(
                {"sessionFile": "/tmp/s.jsonl"}
            )
        )
        assert result["sessionFile"] == "/tmp/s.jsonl"
        assert result["owner"] is None
        assert result["released"] is False

    def test_with_hook(self) -> None:
        async def _acquire(_p: Any) -> Any:
            return {
                "sessionFile": "/tmp/s.jsonl",
                "owner": "owner-1",
                "released": True,
            }

        set_acquire_embedded_attempt_session_file_owner_hook(_acquire)
        result = asyncio.run(
            acquire_embedded_attempt_session_file_owner(
                {"sessionFile": "/tmp/s.jsonl"}
            )
        )
        assert result["owner"] == "owner-1"
        assert result["released"] is True


class TestCreateEmbeddedAttemptSessionLockController:
    def test_basic(self) -> None:
        result = asyncio.run(
            create_embedded_attempt_session_lock_controller({})
        )
        assert result["sessionLockController"] is None
        assert result["withOwnedSessionWriteLock"] is None

    def test_with_hook(self) -> None:
        async def _create(_p: Any) -> Any:
            return {
                "sessionLockController": "lock-ctrl",
                "withOwnedSessionWriteLock": lambda: "acquired",
            }

        set_create_embedded_attempt_session_lock_controller_hook(_create)
        result = asyncio.run(
            create_embedded_attempt_session_lock_controller({})
        )
        assert result["sessionLockController"] == "lock-ctrl"
        assert result["withOwnedSessionWriteLock"]() == "acquired"


class TestInstallPromptSubmissionLockRelease:
    def test_basic(self) -> None:
        assert install_prompt_submission_lock_release({}) is None

    def test_with_hook(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_install_prompt_submission_lock_release_hook(_hook)
        install_prompt_submission_lock_release({"runId": "r1"})
        assert captured[0]["runId"] == "r1"


# ============================================================================
# attempt.tool-call-normalization
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_call_normalization_hooks() -> None:
    set_sanitize_openai_responses_replay_for_stream_hook(
        lambda messages: list(messages or [])
    )
    set_sanitize_replay_tool_call_ids_for_stream_hook(lambda _p: None)
    set_should_apply_replay_tool_call_id_sanitizer_hook(lambda _p: False)
    set_wrap_stream_fn_promote_standalone_text_tool_calls_hook(
        lambda p: p.get("baseFn")
    )
    set_wrap_stream_fn_sanitize_malformed_tool_calls_hook(
        lambda p: p.get("baseFn")
    )
    set_wrap_stream_fn_trim_tool_call_names_hook(
        lambda p: p.get("baseFn")
    )
    yield
    set_sanitize_openai_responses_replay_for_stream_hook(
        lambda messages: list(messages or [])
    )
    set_sanitize_replay_tool_call_ids_for_stream_hook(lambda _p: None)
    set_should_apply_replay_tool_call_id_sanitizer_hook(lambda _p: False)
    set_wrap_stream_fn_promote_standalone_text_tool_calls_hook(
        lambda p: p.get("baseFn")
    )
    set_wrap_stream_fn_sanitize_malformed_tool_calls_hook(
        lambda p: p.get("baseFn")
    )
    set_wrap_stream_fn_trim_tool_call_names_hook(
        lambda p: p.get("baseFn")
    )


class TestToolCallNormalization:
    def test_promote(self) -> None:
        base = "stream-fn-1"
        assert wrap_stream_fn_promote_standalone_text_tool_calls(base) == "stream-fn-1"
        set_wrap_stream_fn_promote_standalone_text_tool_calls_hook(
            lambda _p: "wrapped-1"
        )
        assert (
            wrap_stream_fn_promote_standalone_text_tool_calls("base")
            == "wrapped-1"
        )

    def test_trim(self) -> None:
        assert wrap_stream_fn_trim_tool_call_names("base") == "base"
        set_wrap_stream_fn_trim_tool_call_names_hook(lambda _p: "trimmed")
        assert wrap_stream_fn_trim_tool_call_names("base") == "trimmed"

    def test_should_apply_sanitizer(self) -> None:
        assert should_apply_replay_tool_call_id_sanitizer({}) is False
        set_should_apply_replay_tool_call_id_sanitizer_hook(lambda _p: True)
        assert should_apply_replay_tool_call_id_sanitizer({}) is True

    def test_sanitize_replay_ids(self) -> None:
        assert sanitize_replay_tool_call_ids_for_stream({}) is None
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_sanitize_replay_tool_call_ids_for_stream_hook(_hook)
        sanitize_replay_tool_call_ids_for_stream({"x": 1})
        assert captured[0]["x"] == 1

    def test_sanitize_openai_responses_replay(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        assert (
            sanitize_openai_responses_replay_for_stream(messages)
            == messages
        )
        set_sanitize_openai_responses_replay_for_stream_hook(
            lambda _m: [{"sanitized": True}]
        )
        assert (
            sanitize_openai_responses_replay_for_stream(messages)
            == [{"sanitized": True}]
        )

    def test_wrap_sanitize_malformed(self) -> None:
        assert (
            wrap_stream_fn_sanitize_malformed_tool_calls("base") == "base"
        )
        set_wrap_stream_fn_sanitize_malformed_tool_calls_hook(
            lambda _p: "sanitized"
        )
        assert (
            wrap_stream_fn_sanitize_malformed_tool_calls("base")
            == "sanitized"
        )


# ============================================================================
# attempt.tool-call-argument-repair
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_tool_call_argument_repair_hooks() -> None:
    set_should_repair_malformed_tool_call_arguments_hook(lambda _p: False)
    set_wrap_stream_fn_decode_xai_tool_call_arguments_hook(
        lambda p: p.get("baseFn")
    )
    set_wrap_stream_fn_repair_malformed_tool_call_arguments_hook(
        lambda p: p.get("baseFn")
    )
    yield
    set_should_repair_malformed_tool_call_arguments_hook(lambda _p: False)
    set_wrap_stream_fn_decode_xai_tool_call_arguments_hook(
        lambda p: p.get("baseFn")
    )
    set_wrap_stream_fn_repair_malformed_tool_call_arguments_hook(
        lambda p: p.get("baseFn")
    )


class TestToolCallArgumentRepair:
    def test_should_repair(self) -> None:
        assert should_repair_malformed_tool_call_arguments({}) is False
        set_should_repair_malformed_tool_call_arguments_hook(lambda _p: True)
        assert should_repair_malformed_tool_call_arguments({}) is True

    def test_wrap_repair(self) -> None:
        assert (
            wrap_stream_fn_repair_malformed_tool_call_arguments("base")
            == "base"
        )
        set_wrap_stream_fn_repair_malformed_tool_call_arguments_hook(
            lambda _p: "repaired"
        )
        assert (
            wrap_stream_fn_repair_malformed_tool_call_arguments("base")
            == "repaired"
        )

    def test_wrap_decode_xai(self) -> None:
        assert (
            wrap_stream_fn_decode_xai_tool_call_arguments("base") == "base"
        )
        set_wrap_stream_fn_decode_xai_tool_call_arguments_hook(
            lambda _p: "decoded"
        )
        assert (
            wrap_stream_fn_decode_xai_tool_call_arguments("base")
            == "decoded"
        )


# ============================================================================
# attempt.llm-boundary
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_llm_boundary_hooks() -> None:
    set_install_model_prompt_transform_hook(lambda _p: None)
    set_install_runtime_context_message_for_prompt_hook(lambda _p: None)
    set_normalize_current_prompt_text_for_llm_boundary_hook(lambda _p: None)
    set_normalize_messages_for_current_prompt_boundary_hook(lambda _p: None)
    set_normalize_messages_for_llm_boundary_hook(
        lambda messages: list(messages or [])
    )
    yield
    set_install_model_prompt_transform_hook(lambda _p: None)
    set_install_runtime_context_message_for_prompt_hook(lambda _p: None)
    set_normalize_current_prompt_text_for_llm_boundary_hook(lambda _p: None)
    set_normalize_messages_for_current_prompt_boundary_hook(lambda _p: None)
    set_normalize_messages_for_llm_boundary_hook(
        lambda messages: list(messages or [])
    )


class TestLlmBoundary:
    def test_normalize_messages(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        assert normalize_messages_for_llm_boundary(messages) == messages
        set_normalize_messages_for_llm_boundary_hook(
            lambda _m: [{"normalized": True}]
        )
        assert (
            normalize_messages_for_llm_boundary(messages)
            == [{"normalized": True}]
        )

    def test_normalize_messages_for_current_prompt_boundary(self) -> None:
        assert (
            normalize_messages_for_current_prompt_boundary({}) is None
        )
        set_normalize_messages_for_current_prompt_boundary_hook(
            lambda _p: "normalized"
        )
        assert (
            normalize_messages_for_current_prompt_boundary({})
            == "normalized"
        )

    def test_normalize_current_prompt_text(self) -> None:
        assert (
            normalize_current_prompt_text_for_llm_boundary({}) is None
        )

    def test_install_runtime_context_message(self) -> None:
        assert (
            install_runtime_context_message_for_prompt({}) is None
        )

    def test_install_model_prompt_transform(self) -> None:
        assert install_model_prompt_transform({}) is None
        set_install_model_prompt_transform_hook(
            lambda _p: "transformed"
        )
        assert install_model_prompt_transform({}) == "transformed"


# ============================================================================
# attempt.prompt-helpers
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_helpers_hooks() -> None:
    set_build_after_turn_runtime_context_from_usage_hook(lambda _p: None)
    set_build_after_turn_runtime_context_hook(lambda _p: None)
    set_forget_prompt_build_drain_cache_for_run_hook(lambda _r: None)
    set_merge_orphaned_trailing_user_prompt_hook(lambda _p: None)
    set_prepend_system_prompt_addition_hook(lambda _p: None)
    set_resolve_attempt_fs_workspace_only_hook(lambda _p: False)
    set_resolve_attempt_media_task_system_prompt_addition_hook(lambda _p: None)
    set_resolve_prompt_build_hook_result_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_resolve_prompt_mode_for_session_hook(lambda _sk: "full")
    set_should_inject_heartbeat_prompt_hook(lambda _p: False)
    set_should_warn_on_orphaned_user_repair_hook(lambda _p: False)
    yield
    set_build_after_turn_runtime_context_from_usage_hook(lambda _p: None)
    set_build_after_turn_runtime_context_hook(lambda _p: None)
    set_forget_prompt_build_drain_cache_for_run_hook(lambda _r: None)
    set_merge_orphaned_trailing_user_prompt_hook(lambda _p: None)
    set_prepend_system_prompt_addition_hook(lambda _p: None)
    set_resolve_attempt_fs_workspace_only_hook(lambda _p: False)
    set_resolve_attempt_media_task_system_prompt_addition_hook(lambda _p: None)
    set_resolve_prompt_build_hook_result_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_resolve_prompt_mode_for_session_hook(lambda _sk: "full")
    set_should_inject_heartbeat_prompt_hook(lambda _p: False)
    set_should_warn_on_orphaned_user_repair_hook(lambda _p: False)


class TestPromptHelpers:
    def test_forget_drain_cache(self) -> None:
        # Default no-op; ensure it does not raise.
        forget_prompt_build_drain_cache_for_run("r1")
        forget_prompt_build_drain_cache_for_run(None)
        captured: List[Optional[str]] = []

        def _hook(r: Optional[str]) -> None:
            captured.append(r)

        set_forget_prompt_build_drain_cache_for_run_hook(_hook)
        forget_prompt_build_drain_cache_for_run("r2")
        assert captured == ["r2"]

    def test_resolve_prompt_build_hook_result(self) -> None:
        result = asyncio.run(
            resolve_prompt_build_hook_result({})
        )
        assert result is None

        async def _resolve(_p: Any) -> Any:
            return {"result": "ok"}

        set_resolve_prompt_build_hook_result_hook(_resolve)
        result = asyncio.run(
            resolve_prompt_build_hook_result({})
        )
        assert result == {"result": "ok"}

    def test_resolve_prompt_mode_for_session(self) -> None:
        assert resolve_prompt_mode_for_session() == "full"
        assert resolve_prompt_mode_for_session("s1") == "full"
        set_resolve_prompt_mode_for_session_hook(lambda _sk: "minimal")
        assert resolve_prompt_mode_for_session("s1") == "minimal"

    def test_should_inject_heartbeat_prompt(self) -> None:
        assert should_inject_heartbeat_prompt({}) is False
        set_should_inject_heartbeat_prompt_hook(lambda _p: True)
        assert should_inject_heartbeat_prompt({}) is True

    def test_should_warn_on_orphaned_user_repair(self) -> None:
        assert should_warn_on_orphaned_user_repair({}) is False

    def test_merge_orphaned_trailing_user_prompt(self) -> None:
        assert merge_orphaned_trailing_user_prompt({}) is None
        set_merge_orphaned_trailing_user_prompt_hook(
            lambda _p: "merged"
        )
        assert merge_orphaned_trailing_user_prompt({}) == "merged"

    def test_resolve_attempt_fs_workspace_only(self) -> None:
        assert resolve_attempt_fs_workspace_only({}) is False
        set_resolve_attempt_fs_workspace_only_hook(lambda _p: True)
        assert resolve_attempt_fs_workspace_only({}) is True

    def test_prepend_system_prompt_addition(self) -> None:
        assert prepend_system_prompt_addition({}) is None
        set_prepend_system_prompt_addition_hook(
            lambda _p: "addition"
        )
        assert prepend_system_prompt_addition({}) == "addition"

    def test_resolve_attempt_media_task_system_prompt_addition(self) -> None:
        assert (
            resolve_attempt_media_task_system_prompt_addition({}) is None
        )
        set_resolve_attempt_media_task_system_prompt_addition_hook(
            lambda _p: "media-addition"
        )
        assert (
            resolve_attempt_media_task_system_prompt_addition({})
            == "media-addition"
        )

    def test_build_after_turn_runtime_context(self) -> None:
        assert build_after_turn_runtime_context({}) is None
        set_build_after_turn_runtime_context_hook(
            lambda _p: {"ctx": "after-turn"}
        )
        assert build_after_turn_runtime_context({}) == {"ctx": "after-turn"}

    def test_build_after_turn_runtime_context_from_usage(self) -> None:
        assert build_after_turn_runtime_context_from_usage({}) is None


# ============================================================================
# attempt.model-diagnostic-events
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_model_diagnostic_events_hooks() -> None:
    set_wrap_stream_fn_with_diagnostic_model_call_events_hook(
        lambda p: p.get("baseFn")
    )
    yield
    set_wrap_stream_fn_with_diagnostic_model_call_events_hook(
        lambda p: p.get("baseFn")
    )


class TestModelDiagnosticEvents:
    def test_basic(self) -> None:
        assert (
            wrap_stream_fn_with_diagnostic_model_call_events("base")
            == "base"
        )
        set_wrap_stream_fn_with_diagnostic_model_call_events_hook(
            lambda _p: "with-events"
        )
        assert (
            wrap_stream_fn_with_diagnostic_model_call_events("base")
            == "with-events"
        )
