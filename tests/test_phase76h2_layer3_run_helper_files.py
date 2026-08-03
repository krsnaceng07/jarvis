"""Phase 7.6h-2 tests — 31 run/ helper files."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.abortable import (
    abort,
    await_abortable,
    is_aborted,
    make_abortable,
)
from src.agents.embedded_agent_runner.run.auth_profile_failure_policy import (
    format_auth_profile_failure_message,
    resolve_auth_profile_failure_reason,
    set_format_auth_profile_failure_message_auth_profile_failure_policy_hook,
    set_resolve_auth_profile_failure_reason_auth_profile_failure_policy_hook,
)
from src.agents.embedded_agent_runner.run.auth_profile_failure_policy_types import (
    AuthProfileFailureReason as AuthProfileFailureReasonType,
)
from src.agents.embedded_agent_runner.run.auth_profile_success import (
    mark_embedded_run_auth_profile_success,
    report_embedded_run_successful_auth_binding,
    set_mark_embedded_run_auth_profile_success_auth_profile_success_hook,
    set_report_embedded_run_successful_auth_binding_auth_profile_success_hook,
)
from src.agents.embedded_agent_runner.run.auth_store import (
    create_scoped_auth_profile_store,
    set_create_scoped_auth_profile_store_hook,
)
from src.agents.embedded_agent_runner.run.backend import (
    BACKEND_CLAUDE,
    BACKEND_CODEX,
    BACKEND_GEMINI,
    detect_active_backend,
    reset_active_backend_cache,
)
from src.agents.embedded_agent_runner.run.blocked_run_result import (
    build_embedded_run_blocked_result,
    set_build_embedded_run_blocked_result_blocked_hook,
)
from src.agents.embedded_agent_runner.run.compaction_runtime import (
    build_compaction_runtime,
    resolve_compaction_harness,
    set_build_compaction_runtime_compaction_runtime_hook,
    set_resolve_compaction_harness_compaction_runtime_hook,
    set_should_run_compaction_compaction_runtime_hook,
    should_run_compaction,
)
from src.agents.embedded_agent_runner.run.compaction_timeout import (
    DEFAULT_COMPACTION_TIMEOUT_MS,
    resolve_compaction_timeout_ms,
    set_resolve_compaction_timeout_ms_compaction_timeout_hook,
)
from src.agents.embedded_agent_runner.run.context_recovery_state import (
    EmbeddedRunContextRecoveryState,
)
from src.agents.embedded_agent_runner.run.execution_phase_diagnostics import (
    record_execution_phase_diagnostic,
    set_record_execution_phase_diagnostic_hook,
)
from src.agents.embedded_agent_runner.run.failover_observation import (
    create_failover_decision_logger,
    set_create_failover_decision_logger_failover_observation_hook,
)
from src.agents.embedded_agent_runner.run.failover_policy import (
    MAX_BEFORE_AGENT_FINALIZE_REVISIONS,
    merge_retry_failover_reason,
    resolve_run_failover_decision,
    set_merge_retry_failover_reason_failover_policy_hook,
    set_resolve_run_failover_decision_failover_policy_hook,
)
from src.agents.embedded_agent_runner.run.failover_retry_controller import (
    clear_failover_retries,
    record_failover_retry,
    set_should_retry_after_failover_hook,
    should_retry_after_failover,
)
from src.agents.embedded_agent_runner.run.fallbacks import (
    DEFAULT_FALLBACK_THINKING_LEVEL,
    resolve_thinking_fallback,
    set_resolve_thinking_fallback_hook,
)
from src.agents.embedded_agent_runner.run.history_image_prune import (
    prune_history_images,
)
from src.agents.embedded_agent_runner.run.idle_timeout_breaker import (
    set_should_break_on_idle_timeout_hook,
    should_break_on_idle_timeout,
)
from src.agents.embedded_agent_runner.run.message_transform_stream_wrapper import (
    set_wrap_stream_fn_transform_messages_hook,
    wrap_stream_fn_transform_messages,
)
from src.agents.embedded_agent_runner.run.midturn_precheck import (
    run_midturn_precheck,
    set_run_midturn_precheck_hook,
)
from src.agents.embedded_agent_runner.run.model_harness import (
    resolve_embedded_run_effective_model,
    select_embedded_run_harness,
    select_embedded_run_harness_for_prepared_attempts,
    set_resolve_embedded_run_effective_model_model_harness_hook,
    set_select_embedded_run_harness_for_prepared_attempts_model_harness_hook,
    set_select_embedded_run_harness_model_harness_hook,
)
from src.agents.embedded_agent_runner.run.model_setup import (
    resolve_embedded_run_model_setup,
    set_resolve_embedded_run_model_setup_hook,
)
from src.agents.embedded_agent_runner.run.preemptive_compaction_types import (
    PreemptiveCompactionRoute,
)
from src.agents.embedded_agent_runner.run.progress_controller import (
    DEFAULT_PROGRESS_POLL_INTERVAL_MS,
    record_progress_poll,
    set_should_poll_progress_hook,
    should_poll_progress,
)
from src.agents.embedded_agent_runner.run.recovery_message_action_capability import (
    has_recovery_message_action_capability,
    set_has_recovery_message_action_capability_hook,
)
from src.agents.embedded_agent_runner.run.retry_limit import (
    is_within_retry_limit,
    set_is_within_retry_limit_hook,
)
from src.agents.embedded_agent_runner.run.runtime_resolution import (
    resolve_initial_think_level,
    set_resolve_initial_think_level_runtime_resolution_hook,
)
from src.agents.embedded_agent_runner.run.session_bootstrap import (
    build_context_engine_compaction_session_target,
    is_no_real_conversation_compaction_noop,
    reset_no_real_conversation_token_snapshot,
    set_build_context_engine_compaction_session_target_session_bootstrap_hook,
    set_is_no_real_conversation_compaction_noop_session_bootstrap_hook,
    set_reset_no_real_conversation_token_snapshot_session_bootstrap_hook,
)
from src.agents.embedded_agent_runner.run.skill_workshop_attempt_params import (
    resolve_skill_workshop_attempt_params,
    set_resolve_skill_workshop_attempt_params_hook,
)
from src.agents.embedded_agent_runner.run.stream_wrapper import (
    set_wrap_stream_fn_stream_wrapper_hook,
    wrap_stream_fn,
)
from src.agents.embedded_agent_runner.run.terminal_retry_state import (
    get_terminal_retry_state,
    increment_terminal_retry,
    reset_terminal_retry_state,
)
from src.agents.embedded_agent_runner.run.trigger_policy import (
    resolve_trigger_policy,
    set_resolve_trigger_policy_hook,
)


# ============================================================================
# abortable
# ============================================================================


class TestAbortable:
    def test_make_and_abort(self) -> None:
        handle = make_abortable("payload")
        assert handle["value"] == "payload"
        assert is_aborted(handle) is False
        abort(handle)
        assert is_aborted(handle) is True

    def test_is_aborted_non_dict(self) -> None:
        assert is_aborted(None) is False
        assert is_aborted("not a handle") is False

    def test_abort_non_dict(self) -> None:
        # Should not raise.
        abort(None)
        abort("not a handle")

    def test_await_non_dict(self) -> None:
        result = asyncio.run(await_abortable(None))
        assert result is None
        result = asyncio.run(await_abortable("not a handle"))
        assert result is None

    def test_await_with_value(self) -> None:
        handle = make_abortable("hello")
        result = asyncio.run(await_abortable(handle))
        assert result == "hello"


# ============================================================================
# auth-profile-failure-policy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_auth_profile_failure_policy_hooks() -> None:
    set_format_auth_profile_failure_message_auth_profile_failure_policy_hook(
        lambda _p: "auth profile failure"
    )
    set_resolve_auth_profile_failure_reason_auth_profile_failure_policy_hook(
        lambda _p: None
    )
    yield
    set_format_auth_profile_failure_message_auth_profile_failure_policy_hook(
        lambda _p: "auth profile failure"
    )
    set_resolve_auth_profile_failure_reason_auth_profile_failure_policy_hook(
        lambda _p: None
    )


class TestAuthProfileFailurePolicy:
    def test_format(self) -> None:
        assert (
            format_auth_profile_failure_message({})
            == "auth profile failure"
        )
        set_format_auth_profile_failure_message_auth_profile_failure_policy_hook(
            lambda _p: "rate_limited"
        )
        assert (
            format_auth_profile_failure_message({}) == "rate_limited"
        )

    def test_resolve(self) -> None:
        assert resolve_auth_profile_failure_reason({}) is None
        set_resolve_auth_profile_failure_reason_auth_profile_failure_policy_hook(
            lambda _p: "rate_limited"
        )
        assert (
            resolve_auth_profile_failure_reason({}) == "rate_limited"
        )


# ============================================================================
# auth-profile-failure-policy.types
# ============================================================================


class TestAuthProfileFailureReasonType:
    def test_type_alias(self) -> None:
        # The Python port is a re-export of the optional str alias.
        reason: AuthProfileFailureReasonType = None
        assert reason is None
        reason = "rate_limited"
        assert reason == "rate_limited"


# ============================================================================
# auth-profile-success
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_auth_profile_success_hooks() -> None:
    set_mark_embedded_run_auth_profile_success_auth_profile_success_hook(
        lambda _p: None
    )
    set_report_embedded_run_successful_auth_binding_auth_profile_success_hook(
        lambda _p: None
    )
    yield
    set_mark_embedded_run_auth_profile_success_auth_profile_success_hook(
        lambda _p: None
    )
    set_report_embedded_run_successful_auth_binding_auth_profile_success_hook(
        lambda _p: None
    )


class TestAuthProfileSuccess:
    def test_mark(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_mark_embedded_run_auth_profile_success_auth_profile_success_hook(_hook)
        mark_embedded_run_auth_profile_success({"profileId": "p1"})
        assert captured[0]["profileId"] == "p1"

    def test_report(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_report_embedded_run_successful_auth_binding_auth_profile_success_hook(_hook)
        report_embedded_run_successful_auth_binding({"binding": "b1"})
        assert captured[0]["binding"] == "b1"


# ============================================================================
# auth-store
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_auth_store_hooks() -> None:
    set_create_scoped_auth_profile_store_hook(
        lambda _p: {"version": 1, "profiles": {}}
    )
    yield
    set_create_scoped_auth_profile_store_hook(
        lambda _p: {"version": 1, "profiles": {}}
    )


class TestCreateScopedAuthProfileStore:
    def test_basic(self) -> None:
        result = create_scoped_auth_profile_store({})
        assert result["version"] == 1
        assert result["profiles"] == {}

    def test_with_hook(self) -> None:
        set_create_scoped_auth_profile_store_hook(
            lambda _p: {"version": 2, "profiles": {"a": 1}}
        )
        result = create_scoped_auth_profile_store({})
        assert result["version"] == 2
        assert result["profiles"] == {"a": 1}

    def test_non_dict(self) -> None:
        set_create_scoped_auth_profile_store_hook(lambda _p: None)
        result = create_scoped_auth_profile_store({})
        assert result["version"] == 1


# ============================================================================
# backend
# ============================================================================


class TestBackend:
    def test_constants(self) -> None:
        assert BACKEND_CLAUDE == "claude"
        assert BACKEND_CODEX == "codex"
        assert BACKEND_GEMINI == "gemini"

    def test_detect_default(self) -> None:
        reset_active_backend_cache()
        backend = detect_active_backend()
        assert backend in (BACKEND_CLAUDE, BACKEND_CODEX, BACKEND_GEMINI)

    def test_detect_from_env(self) -> None:
        reset_active_backend_cache()
        import os
        original = os.environ.get("OPENCLAW_BACKEND")
        os.environ["OPENCLAW_BACKEND"] = "codex"
        try:
            backend = detect_active_backend()
            assert backend == "codex"
        finally:
            if original is None:
                os.environ.pop("OPENCLAW_BACKEND", None)
            else:
                os.environ["OPENCLAW_BACKEND"] = original
            reset_active_backend_cache()


# ============================================================================
# blocked-run-result
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_blocked_run_result_hooks() -> None:
    set_build_embedded_run_blocked_result_blocked_hook(lambda _p: {})
    yield
    set_build_embedded_run_blocked_result_blocked_hook(lambda _p: {})


class TestBuildEmbeddedRunBlockedResult:
    def test_basic(self) -> None:
        result = build_embedded_run_blocked_result({})
        assert result["blocked"] is True
        assert result["blockedBy"] is None
        assert result["message"] is None

    def test_with_hook(self) -> None:
        set_build_embedded_run_blocked_result_blocked_hook(
            lambda _p: {
                "blocked": True,
                "blockedBy": "policy",
                "message": "blocked by content policy",
            }
        )
        result = build_embedded_run_blocked_result({})
        assert result["blockedBy"] == "policy"
        assert result["message"] == "blocked by content policy"


# ============================================================================
# compaction-runtime
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_compaction_runtime_hooks() -> None:
    set_build_compaction_runtime_compaction_runtime_hook(lambda _p: None)
    set_resolve_compaction_harness_compaction_runtime_hook(lambda _p: None)
    set_should_run_compaction_compaction_runtime_hook(lambda _p: False)
    yield
    set_build_compaction_runtime_compaction_runtime_hook(lambda _p: None)
    set_resolve_compaction_harness_compaction_runtime_hook(lambda _p: None)
    set_should_run_compaction_compaction_runtime_hook(lambda _p: False)


class TestCompactionRuntime:
    def test_should_run(self) -> None:
        assert should_run_compaction({}) is False
        set_should_run_compaction_compaction_runtime_hook(lambda _p: True)
        assert should_run_compaction({}) is True

    def test_resolve_harness(self) -> None:
        assert resolve_compaction_harness({}) is None
        set_resolve_compaction_harness_compaction_runtime_hook(
            lambda _p: "harness-1"
        )
        assert resolve_compaction_harness({}) == "harness-1"

    def test_build_runtime(self) -> None:
        assert build_compaction_runtime({}) is None
        set_build_compaction_runtime_compaction_runtime_hook(
            lambda _p: {"ready": True}
        )
        assert build_compaction_runtime({}) == {"ready": True}


# ============================================================================
# compaction-timeout
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_compaction_timeout_hooks() -> None:
    set_resolve_compaction_timeout_ms_compaction_timeout_hook(
        lambda _p: DEFAULT_COMPACTION_TIMEOUT_MS
    )
    yield
    set_resolve_compaction_timeout_ms_compaction_timeout_hook(
        lambda _p: DEFAULT_COMPACTION_TIMEOUT_MS
    )


class TestCompactionTimeout:
    def test_default(self) -> None:
        assert DEFAULT_COMPACTION_TIMEOUT_MS == 180_000
        assert resolve_compaction_timeout_ms() == 180_000

    def test_with_hook(self) -> None:
        set_resolve_compaction_timeout_ms_compaction_timeout_hook(
            lambda _p: 60_000
        )
        assert resolve_compaction_timeout_ms() == 60_000


# ============================================================================
# context-recovery-state
# ============================================================================


class TestContextRecoveryState:
    def test_type(self) -> None:
        state: EmbeddedRunContextRecoveryState = {
            "overflowCompactionAttempts": 0,
            "timeoutCompactionAttempts": 0,
        }
        assert state["overflowCompactionAttempts"] == 0


# ============================================================================
# execution-phase-diagnostics
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_execution_phase_diagnostics_hooks() -> None:
    set_record_execution_phase_diagnostic_hook(lambda _p: None)
    yield
    set_record_execution_phase_diagnostic_hook(lambda _p: None)


class TestExecutionPhaseDiagnostics:
    def test_record(self) -> None:
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_record_execution_phase_diagnostic_hook(_hook)
        record_execution_phase_diagnostic({"phase": "tool-call"})
        assert captured[0]["phase"] == "tool-call"


# ============================================================================
# failover-observation
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_failover_observation_hooks() -> None:
    set_create_failover_decision_logger_failover_observation_hook(lambda _p: {})
    yield
    set_create_failover_decision_logger_failover_observation_hook(lambda _p: {})


class TestFailoverObservation:
    def test_basic(self) -> None:
        assert create_failover_decision_logger({}) == {}
        set_create_failover_decision_logger_failover_observation_hook(
            lambda _p: {"log": "x"}
        )
        assert create_failover_decision_logger({}) == {"log": "x"}


# ============================================================================
# failover-policy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_failover_policy_hooks() -> None:
    set_merge_retry_failover_reason_failover_policy_hook(
        lambda cur, _new: cur
    )
    set_resolve_run_failover_decision_failover_policy_hook(lambda _p: None)
    yield
    set_merge_retry_failover_reason_failover_policy_hook(
        lambda cur, _new: cur
    )
    set_resolve_run_failover_decision_failover_policy_hook(lambda _p: None)


class TestFailoverPolicy:
    def test_max_revisions(self) -> None:
        assert MAX_BEFORE_AGENT_FINALIZE_REVISIONS == 1

    def test_resolve(self) -> None:
        result = resolve_run_failover_decision({})
        assert result["action"] == "continue_normal"
        assert result["reason"] is None
        set_resolve_run_failover_decision_failover_policy_hook(
            lambda _p: {"action": "retry", "reason": "rate_limit"}
        )
        result = resolve_run_failover_decision({})
        assert result["action"] == "retry"
        assert result["reason"] == "rate_limit"

    def test_merge(self) -> None:
        assert merge_retry_failover_reason("a", "b") == "a"
        set_merge_retry_failover_reason_failover_policy_hook(
            lambda _cur, new: new
        )
        assert merge_retry_failover_reason("a", "b") == "b"


# ============================================================================
# failover-retry-controller
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_failover_retry_controller_hooks() -> None:
    set_should_retry_after_failover_hook(lambda _p: False)
    yield
    set_should_retry_after_failover_hook(lambda _p: False)


class TestFailoverRetryController:
    def test_should_retry(self) -> None:
        assert should_retry_after_failover({}) is False
        set_should_retry_after_failover_hook(lambda _p: True)
        assert should_retry_after_failover({}) is True

    def test_record_and_clear(self) -> None:
        assert record_failover_retry(None) == 0
        assert record_failover_retry("r1") == 1
        assert record_failover_retry("r1") == 2
        clear_failover_retries("r1")
        assert record_failover_retry("r1") == 1


# ============================================================================
# fallbacks
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_fallbacks_hooks() -> None:
    set_resolve_thinking_fallback_hook(lambda _p: DEFAULT_FALLBACK_THINKING_LEVEL)
    yield
    set_resolve_thinking_fallback_hook(lambda _p: DEFAULT_FALLBACK_THINKING_LEVEL)


class TestFallbacks:
    def test_default(self) -> None:
        assert DEFAULT_FALLBACK_THINKING_LEVEL == "medium"
        assert resolve_thinking_fallback({}) == "medium"

    def test_with_hook(self) -> None:
        set_resolve_thinking_fallback_hook(lambda _p: "low")
        assert resolve_thinking_fallback({}) == "low"


# ============================================================================
# history-image-prune
# ============================================================================


class TestHistoryImagePrune:
    def test_basic(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "image", "src": "x"},
                ],
            },
        ]
        result = prune_history_images(messages)
        assert len(result) == 2
        # First message has no content array, just text.
        assert result[0]["content"] == "hi"
        # Second message had images stripped.
        assert len(result[1]["content"]) == 1
        assert result[1]["content"][0]["type"] == "text"

    def test_empty(self) -> None:
        assert prune_history_images([]) == []

    def test_non_list(self) -> None:
        assert prune_history_images("not a list") == []  # type: ignore[arg-type]


# ============================================================================
# idle-timeout-breaker
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_idle_timeout_breaker_hooks() -> None:
    set_should_break_on_idle_timeout_hook(lambda _p: False)
    yield
    set_should_break_on_idle_timeout_hook(lambda _p: False)


class TestIdleTimeoutBreaker:
    def test_should_break(self) -> None:
        assert should_break_on_idle_timeout({}) is False
        set_should_break_on_idle_timeout_hook(lambda _p: True)
        assert should_break_on_idle_timeout({}) is True


# ============================================================================
# message-transform-stream-wrapper
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_message_transform_stream_wrapper_hooks() -> None:
    set_wrap_stream_fn_transform_messages_hook(lambda p: p.get("baseFn"))
    yield
    set_wrap_stream_fn_transform_messages_hook(lambda p: p.get("baseFn"))


class TestMessageTransformStreamWrapper:
    def test_basic(self) -> None:
        assert wrap_stream_fn_transform_messages("base") == "base"
        set_wrap_stream_fn_transform_messages_hook(lambda _p: "transformed")
        assert wrap_stream_fn_transform_messages("base") == "transformed"


# ============================================================================
# midturn-precheck
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_midturn_precheck_hooks() -> None:
    set_run_midturn_precheck_hook(lambda _p: asyncio.sleep(0))
    yield
    set_run_midturn_precheck_hook(lambda _p: asyncio.sleep(0))


class TestMidturnPrecheck:
    def test_basic(self) -> None:
        result = asyncio.run(run_midturn_precheck({}))
        assert result["outcome"] == "continue"
        assert result["result"] is None

    def test_with_hook(self) -> None:
        async def _run(_p: Any) -> Any:
            return {"outcome": "block", "result": "policy"}

        set_run_midturn_precheck_hook(_run)
        result = asyncio.run(run_midturn_precheck({}))
        assert result["outcome"] == "block"
        assert result["result"] == "policy"


# ============================================================================
# model-harness
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_model_harness_hooks() -> None:
    set_resolve_embedded_run_effective_model_model_harness_hook(
        lambda p: {"effectiveModel": p.get("runtimeModel")}
    )
    set_select_embedded_run_harness_for_prepared_attempts_model_harness_hook(
        lambda _m, _a: {"id": "openclaw", "authBootstrap": None}
    )
    set_select_embedded_run_harness_model_harness_hook(
        lambda _p: {"id": "openclaw", "authBootstrap": None}
    )
    yield
    set_resolve_embedded_run_effective_model_model_harness_hook(
        lambda p: {"effectiveModel": p.get("runtimeModel")}
    )
    set_select_embedded_run_harness_for_prepared_attempts_model_harness_hook(
        lambda _m, _a: {"id": "openclaw", "authBootstrap": None}
    )
    set_select_embedded_run_harness_model_harness_hook(
        lambda _p: {"id": "openclaw", "authBootstrap": None}
    )


class TestModelHarness:
    def test_resolve_effective_model(self) -> None:
        result = resolve_embedded_run_effective_model(
            {"runtimeModel": {"id": "m1"}}
        )
        assert result["effectiveModel"]["id"] == "m1"
        set_resolve_embedded_run_effective_model_model_harness_hook(
            lambda _p: {"effectiveModel": {"id": "m2"}}
        )
        result = resolve_embedded_run_effective_model({})
        assert result["effectiveModel"]["id"] == "m2"

    def test_select_harness(self) -> None:
        result = select_embedded_run_harness({})
        assert result["id"] == "openclaw"
        set_select_embedded_run_harness_model_harness_hook(
            lambda _p: {"id": "harness-1"}
        )
        result = select_embedded_run_harness({})
        assert result["id"] == "harness-1"

    def test_select_harness_for_prepared_attempts(self) -> None:
        result = select_embedded_run_harness_for_prepared_attempts(
            {"id": "m1"}, []
        )
        assert result["id"] == "openclaw"
        set_select_embedded_run_harness_for_prepared_attempts_model_harness_hook(
            lambda _m, _a: {"id": "harness-1"}
        )
        result = select_embedded_run_harness_for_prepared_attempts(
            {"id": "m1"}, []
        )
        assert result["id"] == "harness-1"


# ============================================================================
# model-setup
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_model_setup_hooks() -> None:
    set_resolve_embedded_run_model_setup_hook(lambda _p: asyncio.sleep(0))
    yield
    set_resolve_embedded_run_model_setup_hook(lambda _p: asyncio.sleep(0))


class TestModelSetup:
    def test_basic(self) -> None:
        result = asyncio.run(
            resolve_embedded_run_model_setup({})
        )
        assert result["model"] == {}
        assert result["provider"] == ""
        assert result["agentHarness"]["id"] == "openclaw"

    def test_with_hook(self) -> None:
        async def _resolve(_p: Any) -> Any:
            return {
                "model": {"id": "m1"},
                "provider": "p1",
                "modelId": "m1",
                "agentHarness": {"id": "harness-1"},
            }

        set_resolve_embedded_run_model_setup_hook(_resolve)
        result = asyncio.run(
            resolve_embedded_run_model_setup({})
        )
        assert result["model"]["id"] == "m1"
        assert result["agentHarness"]["id"] == "harness-1"


# ============================================================================
# preemptive-compaction.types
# ============================================================================


class TestPreemptiveCompactionRoute:
    def test_type(self) -> None:
        route: PreemptiveCompactionRoute = "compact"
        assert route == "compact"


# ============================================================================
# progress-controller
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_progress_controller_hooks() -> None:
    set_should_poll_progress_hook(lambda _p: False)
    yield
    set_should_poll_progress_hook(lambda _p: False)


class TestProgressController:
    def test_constant(self) -> None:
        assert DEFAULT_PROGRESS_POLL_INTERVAL_MS == 5_000

    def test_should_poll(self) -> None:
        assert should_poll_progress({}) is False
        set_should_poll_progress_hook(lambda _p: True)
        assert should_poll_progress({}) is True

    def test_record(self) -> None:
        assert record_progress_poll(None) == 0
        ts = record_progress_poll("r1")
        assert ts > 0


# ============================================================================
# recovery-message-action-capability
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_recovery_message_action_capability_hooks() -> None:
    set_has_recovery_message_action_capability_hook(lambda _p: False)
    yield
    set_has_recovery_message_action_capability_hook(lambda _p: False)


class TestRecoveryMessageActionCapability:
    def test_has_capability(self) -> None:
        assert has_recovery_message_action_capability({}) is False
        set_has_recovery_message_action_capability_hook(lambda _p: True)
        assert has_recovery_message_action_capability({}) is True


# ============================================================================
# retry-limit
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_retry_limit_hooks() -> None:
    set_is_within_retry_limit_hook(lambda _p: True)
    yield
    set_is_within_retry_limit_hook(lambda _p: True)


class TestRetryLimit:
    def test_within(self) -> None:
        assert is_within_retry_limit({}) is True
        set_is_within_retry_limit_hook(lambda _p: False)
        assert is_within_retry_limit({}) is False


# ============================================================================
# runtime-resolution
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_runtime_resolution_hooks() -> None:
    set_resolve_initial_think_level_runtime_resolution_hook(lambda _p: "medium")
    yield
    set_resolve_initial_think_level_runtime_resolution_hook(lambda _p: "medium")


class TestRuntimeResolution:
    def test_resolve(self) -> None:
        assert resolve_initial_think_level({}) == "medium"
        set_resolve_initial_think_level_runtime_resolution_hook(
            lambda _p: "high"
        )
        assert resolve_initial_think_level({}) == "high"


# ============================================================================
# session-bootstrap
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_session_bootstrap_hooks() -> None:
    set_build_context_engine_compaction_session_target_session_bootstrap_hook(
        lambda _p: {}
    )
    set_is_no_real_conversation_compaction_noop_session_bootstrap_hook(
        lambda _p: False
    )
    set_reset_no_real_conversation_token_snapshot_session_bootstrap_hook(
        lambda _p: None
    )
    yield
    set_build_context_engine_compaction_session_target_session_bootstrap_hook(
        lambda _p: {}
    )
    set_is_no_real_conversation_compaction_noop_session_bootstrap_hook(
        lambda _p: False
    )
    set_reset_no_real_conversation_token_snapshot_session_bootstrap_hook(
        lambda _p: None
    )


class TestSessionBootstrap:
    def test_build_session_target(self) -> None:
        assert build_context_engine_compaction_session_target({}) == {}
        set_build_context_engine_compaction_session_target_session_bootstrap_hook(
            lambda _p: {"sessionId": "s1"}
        )
        assert build_context_engine_compaction_session_target({}) == {"sessionId": "s1"}

    def test_is_noop(self) -> None:
        assert is_no_real_conversation_compaction_noop({}) is False
        set_is_no_real_conversation_compaction_noop_session_bootstrap_hook(
            lambda _p: True
        )
        assert is_no_real_conversation_compaction_noop({}) is True

    def test_reset_snapshot(self) -> None:
        # Default is no-op; should not raise.
        reset_no_real_conversation_token_snapshot({})
        captured: List[Dict[str, Any]] = []

        def _hook(p: Dict[str, Any]) -> None:
            captured.append(p)

        set_reset_no_real_conversation_token_snapshot_session_bootstrap_hook(_hook)
        reset_no_real_conversation_token_snapshot({"x": 1})
        assert captured[0]["x"] == 1


# ============================================================================
# skill-workshop-attempt-params
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_skill_workshop_attempt_params_hooks() -> None:
    set_resolve_skill_workshop_attempt_params_hook(lambda _p: {})
    yield
    set_resolve_skill_workshop_attempt_params_hook(lambda _p: {})


class TestSkillWorkshopAttemptParams:
    def test_basic(self) -> None:
        assert resolve_skill_workshop_attempt_params({}) == {}
        set_resolve_skill_workshop_attempt_params_hook(
            lambda _p: {"skill": "search"}
        )
        assert resolve_skill_workshop_attempt_params({}) == {"skill": "search"}


# ============================================================================
# stream-wrapper
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_stream_wrapper_hooks() -> None:
    set_wrap_stream_fn_stream_wrapper_hook(lambda p: p.get("baseFn"))
    yield
    set_wrap_stream_fn_stream_wrapper_hook(lambda p: p.get("baseFn"))


class TestStreamWrapper:
    def test_basic(self) -> None:
        assert wrap_stream_fn("base") == "base"
        set_wrap_stream_fn_stream_wrapper_hook(lambda _p: "wrapped")
        assert wrap_stream_fn("base") == "wrapped"


# ============================================================================
# terminal-retry-state
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_terminal_retry_counter() -> None:
    """Clear process-local counter so tests don't leak state between runs."""
    reset_terminal_retry_state("r1")
    yield
    reset_terminal_retry_state("r1")


class TestTerminalRetryState:
    def test_get_set(self) -> None:
        assert get_terminal_retry_state(None) == {"retries": 0}
        assert get_terminal_retry_state("") == {"retries": 0}
        assert get_terminal_retry_state("r1") == {"retries": 0}
        assert increment_terminal_retry("r1") == 1
        assert increment_terminal_retry("r1") == 2
        assert get_terminal_retry_state("r1") == {"retries": 2}

    def test_reset(self) -> None:
        increment_terminal_retry("r1")
        assert get_terminal_retry_state("r1") == {"retries": 1}
        reset_terminal_retry_state("r1")
        assert get_terminal_retry_state("r1") == {"retries": 0}

    def test_increment_none(self) -> None:
        assert increment_terminal_retry(None) == 0


# ============================================================================
# trigger-policy
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_trigger_policy_hooks() -> None:
    set_resolve_trigger_policy_hook(lambda _p: {})
    yield
    set_resolve_trigger_policy_hook(lambda _p: {})


class TestTriggerPolicy:
    def test_basic(self) -> None:
        assert resolve_trigger_policy({}) == {}
        set_resolve_trigger_policy_hook(lambda _p: {"trigger": "cron"})
        assert resolve_trigger_policy({}) == {"trigger": "cron"}
