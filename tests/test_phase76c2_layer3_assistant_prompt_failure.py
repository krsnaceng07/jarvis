"""Phase 7.6c-2 tests — assistant-failover + assistant-failure + prompt-failure."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.assistant_failover import (
    MAX_EMPTY_ERROR_RETRIES_DEFAULT,
    MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES_DEFAULT,
    handle_assistant_failover,
    is_short_window_rate_limit_message,
    set_classify_rate_limit_window_hook,
    set_format_assistant_error_text_hook,
    set_format_billing_error_message_hook,
    set_is_timeout_error_message_hook,
    set_merge_retry_failover_reason_hook,
    set_resolve_failover_status_hook,
    set_resolve_run_failover_decision_hook,
    set_sanitize_for_log_hook,
)
from src.agents.embedded_agent_runner.run.assistant_failure import (
    MAX_EMPTY_ERROR_RETRIES,
    MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES,
    handle_embedded_assistant_failure,
    set_classify_assistant_failover_reason_hook,
    set_create_failover_decision_logger_hook,
    set_handle_assistant_failover_hook,
    set_has_only_assistant_reasoning_content_failure_hook,
    set_is_auth_assistant_error_hook,
    set_is_billing_assistant_error_hook,
    set_is_failover_assistant_error_hook,
    set_is_generic_unknown_stream_error_message_hook,
    set_is_rate_limit_assistant_error_hook,
    set_parse_image_dimension_error_hook,
    set_pick_fallback_thinking_level_hook,
    set_resolve_session_suspension_reason_hook,
)
from src.agents.embedded_agent_runner.run.prompt_failure import (
    handle_embedded_prompt_failure,
    set_build_embedded_run_blocked_result_hook,
    set_classify_failover_reason_hook,
    set_coerce_to_failover_error_hook,
    set_create_failover_decision_logger_hook,
    set_describe_failover_error_hook,
    set_is_failover_error_message_hook,
    set_is_short_window_rate_limit_message_hook,
    set_merge_retry_failover_reason_hook,
    set_parse_image_size_error_hook,
    set_pick_fallback_thinking_level_hook,
    set_resolve_failover_status_hook,
    set_resolve_run_failover_decision_hook,
    set_resolve_session_suspension_reason_hook,
)


# ============================================================================
# assistant-failover: constants
# ============================================================================


class TestAssistantFailoverConstants:
    def test_defaults(self) -> None:
        assert MAX_EMPTY_ERROR_RETRIES_DEFAULT == 3
        assert MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES_DEFAULT == 1


# ============================================================================
# assistant-failover: isShortWindowRateLimitMessage
# ============================================================================


class TestIsShortWindowRateLimitMessage:
    def test_no_message(self) -> None:
        assert is_short_window_rate_limit_message(None) is False
        assert is_short_window_rate_limit_message("") is False

    def test_non_short(self) -> None:
        set_classify_rate_limit_window_hook(
            lambda _m: {"kind": "long", "retryAfterSeconds": 60}
        )
        assert is_short_window_rate_limit_message("rate limit") is False

    def test_short(self) -> None:
        set_classify_rate_limit_window_hook(
            lambda _m: {"kind": "short", "retryAfterSeconds": 1}
        )
        assert is_short_window_rate_limit_message("rate limit") is True

    def test_none_kind(self) -> None:
        set_classify_rate_limit_window_hook(
            lambda _m: {"kind": "none", "retryAfterSeconds": None}
        )
        assert is_short_window_rate_limit_message("rate limit") is False


# ============================================================================
# assistant-failover: handleAssistantFailover
# ============================================================================


class TestHandleAssistantFailover:
    def test_no_decision(self) -> None:
        result = asyncio.run(
            handle_assistant_failover(
                {
                    "initialDecision": None,
                    "aborted": False,
                    "externalAbort": False,
                }
            )
        )
        assert result["action"] == "continue_normal"

    def test_aborted(self) -> None:
        result = asyncio.run(
            handle_assistant_failover(
                {
                    "initialDecision": {"action": "retry"},
                    "aborted": True,
                    "externalAbort": False,
                }
            )
        )
        assert result["action"] == "continue_normal"

    def test_external_abort(self) -> None:
        result = asyncio.run(
            handle_assistant_failover(
                {
                    "initialDecision": {"action": "retry"},
                    "aborted": False,
                    "externalAbort": True,
                }
            )
        )
        assert result["action"] == "continue_normal"

    def test_with_decision(self) -> None:
        result = asyncio.run(
            handle_assistant_failover(
                {
                    "initialDecision": {"action": "retry"},
                    "aborted": False,
                    "externalAbort": False,
                }
            )
        )
        assert result["action"] == "continue_normal"
        assert "overloadProfileRotations" in result

    def test_overload_profile_rotations_preserved(self) -> None:
        result = asyncio.run(
            handle_assistant_failover(
                {
                    "initialDecision": {"action": "retry"},
                    "aborted": False,
                    "externalAbort": False,
                    "overloadProfileRotations": 2,
                }
            )
        )
        assert result["overloadProfileRotations"] == 2


# ============================================================================
# assistant-failover: hook setters
# ============================================================================


class TestAssistantFailoverHookSetters:
    def test_setters(self) -> None:
        set_format_assistant_error_text_hook(lambda _p: "x")
        set_format_billing_error_message_hook(lambda _p: "x")
        set_is_timeout_error_message_hook(lambda _t, _c: False)
        set_merge_retry_failover_reason_hook(lambda _c, _n: None)
        set_resolve_failover_status_hook(lambda _e: 0)
        set_resolve_run_failover_decision_hook(lambda _p: None)
        set_sanitize_for_log_hook(lambda t: t)


# ============================================================================
# assistant-failure: constants
# ============================================================================


class TestAssistantFailureConstants:
    def test_max_retries(self) -> None:
        assert MAX_EMPTY_ERROR_RETRIES == 3
        assert MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES == 1


# ============================================================================
# assistant-failure: handleEmbeddedAssistantFailure
# ============================================================================


class TestHandleEmbeddedAssistantFailure:
    def test_basic(self) -> None:
        result = asyncio.run(
            handle_embedded_assistant_failure(
                {
                    "runParams": {},
                    "attempt": {},
                    "thinkLevel": "medium",
                    "emptyErrorRetries": 0,
                    "overloadProfileRotations": 0,
                    "sameModelIdleTimeoutRetries": 0,
                }
            )
        )
        assert result["action"] == "proceed"
        assert result["thinkLevel"] == "medium"
        assert result["emptyErrorRetries"] == 0
        assert result["overloadProfileRotations"] == 0
        assert result["sameModelIdleTimeoutRetries"] == 0
        assert result["authRetryPending"] is False
        assert result["lastRetryFailoverReason"] is None

    def test_preserves_state(self) -> None:
        result = asyncio.run(
            handle_embedded_assistant_failure(
                {
                    "runParams": {},
                    "attempt": {},
                    "thinkLevel": "high",
                    "emptyErrorRetries": 1,
                    "overloadProfileRotations": 2,
                    "sameModelIdleTimeoutRetries": 0,
                }
            )
        )
        assert result["thinkLevel"] == "high"
        assert result["emptyErrorRetries"] == 1
        assert result["overloadProfileRotations"] == 2


# ============================================================================
# assistant-failure: hook setters
# ============================================================================


class TestAssistantFailureHookSetters:
    def test_setters(self) -> None:
        set_classify_assistant_failover_reason_hook(lambda _t, _c: None)
        set_create_failover_decision_logger_hook(lambda _p: None)
        set_handle_assistant_failover_hook(lambda _p: asyncio.sleep(0))
        set_has_only_assistant_reasoning_content_failure_hook(
            lambda _m: False
        )
        set_is_auth_assistant_error_hook(lambda _t, _c: False)
        set_is_billing_assistant_error_hook(lambda _t, _c: False)
        set_is_failover_assistant_error_hook(lambda _t, _c: False)
        set_is_generic_unknown_stream_error_message_hook(lambda _t: False)
        set_is_rate_limit_assistant_error_hook(lambda _t, _c: False)
        set_parse_image_dimension_error_hook(lambda _t: None)
        set_pick_fallback_thinking_level_hook(lambda _l, _a: "medium")
        set_resolve_session_suspension_reason_hook(lambda _p: None)


# ============================================================================
# prompt-failure: handleEmbeddedPromptFailure
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_prompt_failure_hooks() -> None:
    set_build_embedded_run_blocked_result_hook(lambda _p: None)
    set_classify_failover_reason_hook(lambda _t, _c: None)
    set_coerce_to_failover_error_hook(lambda _e: None)
    set_create_failover_decision_logger_hook(lambda _p: None)
    set_describe_failover_error_hook(lambda _e: "")
    set_is_failover_error_message_hook(lambda _t, _c: False)
    set_is_short_window_rate_limit_message_hook(lambda _m: False)
    set_merge_retry_failover_reason_hook(lambda _c, _n: None)
    set_parse_image_size_error_hook(lambda _t: None)
    set_pick_fallback_thinking_level_hook(lambda _l, _a: "medium")
    set_resolve_failover_status_hook(lambda _e: 0)
    set_resolve_run_failover_decision_hook(lambda _p: None)
    set_resolve_session_suspension_reason_hook(lambda _p: None)
    yield
    set_classify_failover_reason_hook(lambda _t, _c: None)
    set_is_failover_error_message_hook(lambda _t, _c: False)


class TestHandleEmbeddedPromptFailure:
    def test_basic(self) -> None:
        result = asyncio.run(
            handle_embedded_prompt_failure(
                {
                    "runParams": {},
                    "attempt": {
                        "runId": "r1",
                        "sessionId": "s1",
                        "sessionKey": "k1",
                        "sessionFile": "/tmp/s.jsonl",
                    },
                    "promptError": "rate limit exceeded",
                    "thinkLevel": "medium",
                    "buildErrorAgentMeta": lambda: {
                        "provider": "p1",
                        "model": "m1",
                    },
                    "failureSignal": None,
                }
            )
        )
        assert result["action"] == "complete"
        assert result["result"]["runId"] == "r1"
        assert result["result"]["sessionId"] == "s1"
        assert result["result"]["promptError"] == "rate limit exceeded"
        assert result["result"]["agentMeta"]["provider"] == "p1"
        assert result["result"]["payloads"] == []
        assert result["thinkLevel"] == "medium"
        assert result["authRetryPending"] is False

    def test_no_agent_meta(self) -> None:
        result = asyncio.run(
            handle_embedded_prompt_failure(
                {
                    "runParams": {},
                    "attempt": {"sessionId": "s1"},
                    "promptError": "boom",
                    "thinkLevel": "high",
                }
            )
        )
        assert result["action"] == "complete"
        assert result["result"]["agentMeta"] == {}
        assert result["thinkLevel"] == "high"


# ============================================================================
# prompt-failure: hook setters
# ============================================================================


class TestPromptFailureHookSetters:
    def test_setters(self) -> None:
        set_build_embedded_run_blocked_result_hook(lambda _p: None)
        set_classify_failover_reason_hook(lambda _t, _c: None)
        set_coerce_to_failover_error_hook(lambda _e: None)
        set_create_failover_decision_logger_hook(lambda _p: None)
        set_describe_failover_error_hook(lambda _e: "")
        set_is_failover_error_message_hook(lambda _t, _c: False)
        set_is_short_window_rate_limit_message_hook(lambda _m: False)
        set_merge_retry_failover_reason_hook(lambda _c, _n: None)
        set_parse_image_size_error_hook(lambda _t: None)
        set_pick_fallback_thinking_level_hook(lambda _l, _a: "medium")
        set_resolve_failover_status_hook(lambda _e: 0)
        set_resolve_run_failover_decision_hook(lambda _p: None)
        set_resolve_session_suspension_reason_hook(lambda _p: None)
