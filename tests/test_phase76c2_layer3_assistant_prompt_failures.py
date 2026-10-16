"""Phase 7.6c-2 tests — assistant-failure + assistant-failover + prompt-failure."""
from __future__ import annotations

import asyncio


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
# assistant-failover: isShortWindowRateLimitMessage
# ============================================================================


class TestIsShortWindowRateLimitMessage:
    def setup_method(self) -> None:
        set_classify_rate_limit_window_hook(
            lambda _m: {"kind": "none", "retryAfterSeconds": None}
        )

    def test_short_window(self) -> None:
        set_classify_rate_limit_window_hook(
            lambda _m: {"kind": "short", "retryAfterSeconds": 60}
        )
        assert is_short_window_rate_limit_message("rate limit hit") is True

    def test_long_window(self) -> None:
        set_classify_rate_limit_window_hook(
            lambda _m: {"kind": "long", "retryAfterSeconds": 3600}
        )
        assert is_short_window_rate_limit_message("rate limit hit") is False

    def test_no_window(self) -> None:
        assert is_short_window_rate_limit_message("rate limit hit") is False

    def test_empty(self) -> None:
        assert is_short_window_rate_limit_message("") is False
        assert is_short_window_rate_limit_message(None) is False  # type: ignore[arg-type]


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

    def test_continue_normal(self) -> None:
        result = asyncio.run(
            handle_assistant_failover(
                {
                    "initialDecision": {"action": "continue_normal"},
                    "aborted": False,
                    "externalAbort": False,
                }
            )
        )
        assert result["action"] == "continue_normal"
        assert "overloadProfileRotations" in result


class TestAssistantFailoverConstants:
    def test_constants(self) -> None:
        assert MAX_EMPTY_ERROR_RETRIES_DEFAULT == 3
        assert MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES_DEFAULT == 1


class TestAssistantFailoverHookSetters:
    def test_setters(self) -> None:
        set_format_assistant_error_text_hook(lambda _p: "")
        set_format_billing_error_message_hook(lambda _p: "")
        set_is_timeout_error_message_hook(lambda _t, _c: False)
        set_merge_retry_failover_reason_hook(lambda _a, _b: None)
        set_resolve_failover_status_hook(lambda _e: 0)
        set_resolve_run_failover_decision_hook(lambda _p: None)
        set_sanitize_for_log_hook(lambda t: t)


# ============================================================================
# assistant-failure
# ============================================================================


class TestAssistantFailureConstants:
    def test_constants(self) -> None:
        assert MAX_EMPTY_ERROR_RETRIES == 3
        assert MAX_SAME_MODEL_IDLE_TIMEOUT_RETRIES == 1


class TestHandleEmbeddedAssistantFailure:
    def test_basic(self) -> None:
        result = asyncio.run(
            handle_embedded_assistant_failure(
                {
                    "runParams": {},
                    "attempt": {"runId": "r1"},
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
        assert result["assistantProfileFailureReason"] is None

    def test_with_counts(self) -> None:
        result = asyncio.run(
            handle_embedded_assistant_failure(
                {
                    "runParams": {},
                    "attempt": {},
                    "thinkLevel": "high",
                    "emptyErrorRetries": 2,
                    "overloadProfileRotations": 1,
                    "sameModelIdleTimeoutRetries": 1,
                }
            )
        )
        assert result["emptyErrorRetries"] == 2
        assert result["overloadProfileRotations"] == 1
        assert result["sameModelIdleTimeoutRetries"] == 1


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
# prompt-failure
# ============================================================================


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
                        "agentId": "a1",
                    },
                    "promptError": "boom",
                    "thinkLevel": "medium",
                    "buildErrorAgentMeta": lambda: {"provider": "p1", "model": "m1"},
                }
            )
        )
        assert result["action"] == "complete"
        assert result["result"]["runId"] == "r1"
        assert result["result"]["sessionId"] == "s1"
        assert result["result"]["promptError"] == "boom"
        assert result["result"]["agentMeta"] == {"provider": "p1", "model": "m1"}
        assert result["result"]["payloads"] == []
        assert result["thinkLevel"] == "medium"
        assert result["authRetryPending"] is False
        assert result["lastRetryFailoverReason"] is None

    def test_with_think_level(self) -> None:
        result = asyncio.run(
            handle_embedded_prompt_failure(
                {
                    "runParams": {},
                    "attempt": {},
                    "promptError": None,
                    "thinkLevel": "high",
                    "buildErrorAgentMeta": lambda: {},
                }
            )
        )
        assert result["thinkLevel"] == "high"
        assert result["result"]["promptError"] is None

    def test_empty_agent_meta(self) -> None:
        result = asyncio.run(
            handle_embedded_prompt_failure(
                {
                    "runParams": {},
                    "attempt": {},
                    "promptError": "x",
                    "thinkLevel": "medium",
                    "buildErrorAgentMeta": lambda: {},
                }
            )
        )
        assert result["result"]["agentMeta"] == {}


class TestPromptFailureHookSetters:
    def test_setters(self) -> None:
        set_build_embedded_run_blocked_result_hook(lambda _p: None)
        set_classify_failover_reason_hook(lambda _t, _c: None)
        set_coerce_to_failover_error_hook(lambda _e: None)
        set_create_failover_decision_logger_hook(lambda _p: None)
        set_describe_failover_error_hook(lambda _e: "")
        set_is_failover_error_message_hook(lambda _t, _c: False)
        set_is_short_window_rate_limit_message_hook(lambda _m: False)
        set_merge_retry_failover_reason_hook(lambda _a, _b: None)
        set_parse_image_size_error_hook(lambda _t: None)
        set_pick_fallback_thinking_level_hook(lambda _l, _a: "medium")
        set_resolve_failover_status_hook(lambda _e: 0)
        set_resolve_run_failover_decision_hook(lambda _p: None)
        set_resolve_session_suspension_reason_hook(lambda _p: None)
