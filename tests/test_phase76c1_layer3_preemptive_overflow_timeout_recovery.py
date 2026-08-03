"""Phase 7.6c-1 tests — preemptive-compaction + overflow-context-recovery + timeout-context-recovery."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import pytest

from src.agents.embedded_agent_runner.run.preemptive_compaction import (
    BRANCH_SUMMARY_PREFIX,
    BRANCH_SUMMARY_SUFFIX,
    COMPACTION_SUMMARY_PREFIX,
    COMPACTION_SUMMARY_SUFFIX,
    CONTENT_BLOCK_OVERHEAD_TOKENS,
    ESTIMATED_CHARS_PER_TOKEN,
    IMAGE_BLOCK_TOKENS,
    JSON_PAYLOAD_CHARS_PER_TOKEN,
    MESSAGE_BOUNDARY_OVERHEAD_TOKENS,
    MIN_PROMPT_BUDGET_RATIO,
    MIN_PROMPT_BUDGET_TOKENS,
    PREEMPTIVE_OVERFLOW_ERROR_TEXT,
    SAFETY_MARGIN,
    TOOL_RESULT_CHARS_PER_TOKEN,
    TRUNCATION_ROUTE_BUFFER_TOKENS,
    build_pre_prompt_context_budget_status,
    estimate_json_payload_token_pressure,
    estimate_llm_boundary_token_pressure,
    estimate_rendered_llm_boundary_token_pressure,
    estimate_string_token_pressure,
    format_pre_prompt_precheck_log,
    set_estimate_string_chars_hook,
    set_estimate_tool_result_reduction_potential_hook,
    should_preemptively_compact_before_prompt,
)
from src.agents.embedded_agent_runner.run.overflow_context_recovery import (
    MAX_OVERFLOW_COMPACTION_ATTEMPTS,
    recover_embedded_run_overflow,
    set_build_context_engine_runtime_settings_hook,
    set_build_embedded_compaction_runtime_context_hook,
    set_compact_context_engine_with_safety_timeout_hook,
    set_create_compaction_diag_id_hook,
    set_extract_observed_overflow_token_count_hook,
    set_is_compaction_failure_error_hook,
    set_is_likely_context_overflow_error_hook,
    set_is_no_real_conversation_compaction_noop_hook,
    set_reset_no_real_conversation_token_snapshot_hook,
    set_resolve_compaction_timeout_ms_hook,
    set_resolve_context_engine_capabilities_hook,
    set_run_context_engine_maintenance_hook,
)
from src.agents.embedded_agent_runner.run.timeout_context_recovery import (
    MAX_TIMEOUT_COMPACTION_ATTEMPTS,
    TIMEOUT_COMPACTION_TOKEN_USED_RATIO_THRESHOLD,
    recover_embedded_run_timeout,
    set_build_context_engine_runtime_settings_timeout_hook,
    set_build_embedded_compaction_runtime_context_timeout_hook,
    set_compact_context_engine_with_safety_timeout_timeout_hook,
    set_derive_context_prompt_tokens_hook,
    set_resolve_compaction_timeout_ms_timeout_hook,
    set_run_post_compaction_side_effects_hook,
)


# ============================================================================
# preemptive-compaction: constants
# ============================================================================


class TestPreemptiveCompactionConstants:
    def test_overflow_text(self) -> None:
        assert PREEMPTIVE_OVERFLOW_ERROR_TEXT == (
            "Context overflow: prompt too large for the model (precheck)."
        )

    def test_token_estimates(self) -> None:
        assert ESTIMATED_CHARS_PER_TOKEN == 4
        assert TOOL_RESULT_CHARS_PER_TOKEN == 2
        assert JSON_PAYLOAD_CHARS_PER_TOKEN == 3

    def test_overhead_tokens(self) -> None:
        assert MESSAGE_BOUNDARY_OVERHEAD_TOKENS == 12
        assert CONTENT_BLOCK_OVERHEAD_TOKENS == 6
        assert IMAGE_BLOCK_TOKENS == 2_000
        assert TRUNCATION_ROUTE_BUFFER_TOKENS == 512

    def test_budget(self) -> None:
        assert MIN_PROMPT_BUDGET_RATIO == 0.2
        assert MIN_PROMPT_BUDGET_TOKENS == 8_000
        assert SAFETY_MARGIN == 4_000

    def test_summary_markers(self) -> None:
        assert BRANCH_SUMMARY_PREFIX == "[branch summary]"
        assert BRANCH_SUMMARY_SUFFIX == "[/branch summary]"
        assert COMPACTION_SUMMARY_PREFIX == "[compaction summary]"
        assert COMPACTION_SUMMARY_SUFFIX == "[/compaction summary]"


# ============================================================================
# preemptive-compaction: token-pressure helpers
# ============================================================================


class TestEstimateStringTokenPressure:
    def test_basic(self) -> None:
        result = estimate_string_token_pressure("hello world")
        # 11 chars / 4 chars-per-token = ceil(2.75) = 3
        assert result == 3

    def test_empty(self) -> None:
        assert estimate_string_token_pressure("") == 0

    def test_custom_chars_per_token(self) -> None:
        # 11 chars / 2 chars-per-token = ceil(5.5) = 6
        assert estimate_string_token_pressure("hello world", 2) == 6

    def test_non_string(self) -> None:
        assert estimate_string_token_pressure(None) == 0  # type: ignore[arg-type]

    def test_zero_chars_per_token(self) -> None:
        assert estimate_string_token_pressure("hello", 0) == 0


class TestEstimateJsonPayloadTokenPressure:
    def test_dict(self) -> None:
        result = estimate_json_payload_token_pressure({"a": 1})
        # 7 chars / 3 chars-per-token = ceil(2.33) = 3
        assert result == 3

    def test_list(self) -> None:
        result = estimate_json_payload_token_pressure([1, 2, 3])
        # 7 chars / 3 chars-per-token = 3
        assert result == 3

    def test_non_serializable(self) -> None:
        class Bad:
            pass

        result = estimate_json_payload_token_pressure(Bad())
        # Returns 256 fallback for non-serializable.
        assert result == 256

    def test_zero_chars_per_token(self) -> None:
        assert estimate_json_payload_token_pressure({"a": 1}, 0) == 0


# ============================================================================
# preemptive-compaction: estimateLlmBoundaryTokenPressure
# ============================================================================


class TestEstimateLlmBoundaryTokenPressure:
    def test_empty(self) -> None:
        result = estimate_llm_boundary_token_pressure({"messages": []})
        assert result["estimatedPromptTokens"] == 0
        assert result["source"] == "estimated"

    def test_string_content(self) -> None:
        result = estimate_llm_boundary_token_pressure(
            {"messages": [{"role": "user", "content": "hello world"}]}
        )
        # 12 (boundary) + 3 (string) = 15
        assert result["estimatedPromptTokens"] == 15

    def test_list_content_with_text(self) -> None:
        result = estimate_llm_boundary_token_pressure(
            {
                "messages": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "hello"}],
                    }
                ]
            }
        )
        # 12 (boundary) + 6 (block) + ceil(5/4)=2 (text) = 20
        assert result["estimatedPromptTokens"] == 20

    def test_image_block(self) -> None:
        result = estimate_llm_boundary_token_pressure(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "image", "data": "..."}],
                    }
                ]
            }
        )
        # 12 + 6 + 2000 = 2018
        assert result["estimatedPromptTokens"] == 2018

    def test_unknown_block(self) -> None:
        result = estimate_llm_boundary_token_pressure(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "unknown", "data": "x"}],
                    }
                ]
            }
        )
        # 12 (boundary) + 6 (block) + json token pressure. We don't
        # assert the exact value because the JSON-serialized length
        # depends on the JSON encoder's whitespace policy; just
        # confirm it's in a sensible range.
        assert result["estimatedPromptTokens"] >= 12 + 6 + 1
        assert result["estimatedPromptTokens"] < 12 + 6 + 50


# ============================================================================
# preemptive-compaction: estimateRenderedLlmBoundaryTokenPressure
# ============================================================================


class TestEstimateRenderedLlmBoundaryTokenPressure:
    def test_basic(self) -> None:
        result = estimate_rendered_llm_boundary_token_pressure(
            {"rendered": "hello world"}
        )
        # 11 / 4 = ceil(2.75) = 3
        assert result["estimatedPromptTokens"] == 3
        assert result["source"] == "rendered"
        assert result["renderedChars"] == 11

    def test_empty(self) -> None:
        result = estimate_rendered_llm_boundary_token_pressure(
            {"rendered": ""}
        )
        assert result["estimatedPromptTokens"] == 0


# ============================================================================
# preemptive-compaction: shouldPreemptivelyCompactBeforePrompt
# ============================================================================


class TestShouldPreemptivelyCompactBeforePrompt:
    def setup_method(self) -> None:
        set_estimate_tool_result_reduction_potential_hook(lambda _a: 0)

    def test_no_pressure(self) -> None:
        decision = should_preemptively_compact_before_prompt(
            {
                "prompt": "hi",
                "rendered": "hi",
                "contextWindow": 200_000,
                "reserveTokens": 4_000,
            }
        )
        assert decision["route"] == "none"
        assert decision["shouldCompact"] is False
        assert decision["overflowTokens"] == 0

    def test_with_pressure(self) -> None:
        decision = should_preemptively_compact_before_prompt(
            {
                "prompt": "x" * 8_000,
                "rendered": "x" * 8_000,
                "contextWindow": 10_000,
                "reserveTokens": 4_000,
            }
        )
        assert decision["shouldCompact"] is True
        assert decision["overflowTokens"] > 0

    def test_truncation_route(self) -> None:
        set_estimate_tool_result_reduction_potential_hook(
            lambda _a: 100_000
        )
        decision = should_preemptively_compact_before_prompt(
            {
                "prompt": "x" * 8_000,
                "rendered": "x" * 8_000,
                "contextWindow": 10_000,
                "reserveTokens": 4_000,
            }
        )
        assert decision["shouldCompact"] is True
        assert decision["route"] == "truncate-tool-results"
        assert decision["toolResultReducibleChars"] == 100_000

    def test_compact_route(self) -> None:
        set_estimate_tool_result_reduction_potential_hook(lambda _a: 0)
        decision = should_preemptively_compact_before_prompt(
            {
                "prompt": "x" * 8_000,
                "rendered": "x" * 8_000,
                "contextWindow": 10_000,
                "reserveTokens": 4_000,
            }
        )
        assert decision["shouldCompact"] is True
        assert decision["route"] == "compact"


# ============================================================================
# preemptive-compaction: formatters
# ============================================================================


class TestFormatters:
    def test_format_pre_prompt_precheck_log(self) -> None:
        result = format_pre_prompt_precheck_log(
            {
                "decision": {
                    "route": "compact",
                    "estimatedPromptTokens": 100,
                    "overflowTokens": 50,
                    "toolResultReducibleChars": 0,
                }
            }
        )
        assert "compact" in result
        assert "estimated=100" in result
        assert "overflow=50" in result

    def test_format_pre_prompt_precheck_log_empty(self) -> None:
        result = format_pre_prompt_precheck_log({})
        assert "route=none" in result

    def test_build_pre_prompt_context_budget_status(self) -> None:
        result = build_pre_prompt_context_budget_status(
            {
                "decision": {
                    "route": "compact",
                    "estimatedPromptTokens": 100,
                    "overflowTokens": 50,
                    "toolResultReducibleChars": 0,
                    "effectiveReserveTokens": 4_000,
                }
            }
        )
        assert result["route"] == "compact"
        assert result["estimatedPromptTokens"] == 100
        assert result["overflowTokens"] == 50


# ============================================================================
# preemptive-compaction: hook setters
# ============================================================================


class TestPreemptiveCompactionHookSetters:
    def test_setters(self) -> None:
        set_estimate_string_chars_hook(lambda _t: 0)


# ============================================================================
# overflow-context-recovery
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_overflow_hooks() -> None:
    set_build_context_engine_runtime_settings_hook(lambda _p: None)
    set_build_embedded_compaction_runtime_context_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_compact_context_engine_with_safety_timeout_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_create_compaction_diag_id_hook(lambda: "diag")
    set_extract_observed_overflow_token_count_hook(lambda _t: None)
    set_is_compaction_failure_error_hook(lambda _t: False)
    set_is_likely_context_overflow_error_hook(lambda _t: False)
    set_is_no_real_conversation_compaction_noop_hook(lambda _p: False)
    set_reset_no_real_conversation_token_snapshot_hook(lambda _p: None)
    set_resolve_compaction_timeout_ms_hook(lambda _c: 180_000)
    set_resolve_context_engine_capabilities_hook(lambda _p: None)
    set_run_context_engine_maintenance_hook(lambda _p: asyncio.sleep(0))
    yield
    set_is_likely_context_overflow_error_hook(lambda _t: False)
    set_is_compaction_failure_error_hook(lambda _t: False)
    set_extract_observed_overflow_token_count_hook(lambda _t: None)


class TestOverflowContextRecoveryConstants:
    def test_max_attempts(self) -> None:
        assert MAX_OVERFLOW_COMPACTION_ATTEMPTS == 3


class TestRecoverEmbeddedRunOverflow:
    def test_no_overflow(self) -> None:
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": None,
                    "assistantErrorText": None,
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result == {"action": "none"}

    def test_aborted_skips(self) -> None:
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": True,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result == {"action": "none"}

    def test_no_recovery_allowed(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": False,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result == {"action": "none"}

    def test_no_token_budget(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": None,
                    "attempt": {},
                    "state": {},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result == {"action": "none"}

    def test_retry_with_attempt_count(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {"overflowCompactionAttempts": 0},
                    "attemptCompactionCount": 1,
                }
            )
        )
        assert result == {"action": "retry"}

    def test_retry_without_attempt_count(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {"overflowCompactionAttempts": 0},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result == {"action": "retry"}

    def test_compaction_failure_surfaces(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        set_is_compaction_failure_error_hook(lambda _t: True)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "compaction failed",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {"overflowCompactionAttempts": 0},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result["action"] == "surface"
        assert result["kind"] == "compaction_failure"
        assert "Unable to recover" in result["userText"]

    def test_max_retries_surfaces_overflow(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {},
                    "state": {"overflowCompactionAttempts": 3},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result["action"] == "surface"
        assert result["kind"] == "context_overflow"

    def test_preflight_recovery_estimated_prompt_tokens(self) -> None:
        set_is_likely_context_overflow_error_hook(lambda _t: True)
        set_extract_observed_overflow_token_count_hook(lambda _t: 100_000)
        result = asyncio.run(
            recover_embedded_run_overflow(
                {
                    "aborted": False,
                    "signalOwnedInterruption": False,
                    "promptError": "context overflow",
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "attempt": {
                        "preflightRecovery": {"estimatedPromptTokens": 150_000}
                    },
                    "state": {"overflowCompactionAttempts": 0},
                    "attemptCompactionCount": 0,
                }
            )
        )
        assert result["action"] == "retry"


# ============================================================================
# timeout-context-recovery
# ============================================================================


@pytest.fixture(autouse=True)
def _reset_timeout_hooks() -> None:
    set_build_context_engine_runtime_settings_timeout_hook(lambda _p: None)
    set_build_embedded_compaction_runtime_context_timeout_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_compact_context_engine_with_safety_timeout_timeout_hook(
        lambda _p: asyncio.sleep(0)
    )
    set_derive_context_prompt_tokens_hook(lambda _p: None)
    set_resolve_compaction_timeout_ms_timeout_hook(lambda _c: 180_000)
    set_run_post_compaction_side_effects_hook(lambda _p: asyncio.sleep(0))
    yield
    set_derive_context_prompt_tokens_hook(lambda _p: None)


class TestTimeoutContextRecoveryConstants:
    def test_max_attempts(self) -> None:
        assert MAX_TIMEOUT_COMPACTION_ATTEMPTS == 2

    def test_threshold(self) -> None:
        assert TIMEOUT_COMPACTION_TOKEN_USED_RATIO_THRESHOLD == 0.65


class TestRecoverEmbeddedRunTimeout:
    def test_not_timed_out(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "timedOut": False,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_no_recovery_allowed(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": False,
                    "contextTokenBudget": 200_000,
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_no_token_budget(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": None,
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_signal_owned_interruption_skips(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "timedOut": True,
                    "signalOwnedInterruption": True,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_during_compaction_skips(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": True,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_during_tool_execution_skips(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": True,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_by_run_budget_skips(self) -> None:
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": True,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_low_token_usage_skips(self) -> None:
        set_derive_context_prompt_tokens_hook(lambda _p: 50_000)
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,  # ratio = 50/200 = 0.25 < 0.65
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {},
                }
            )
        )
        assert result is False

    def test_max_attempts_skips(self) -> None:
        set_derive_context_prompt_tokens_hook(lambda _p: 180_000)
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {"timeoutCompactionAttempts": 2},
                }
            )
        )
        assert result is False

    def test_high_token_usage_triggers_recovery(self) -> None:
        set_derive_context_prompt_tokens_hook(lambda _p: 180_000)
        result = asyncio.run(
            recover_embedded_run_timeout(
                {
                    "genericCompactionRecoveryAllowed": True,
                    "contextTokenBudget": 200_000,  # ratio = 180/200 = 0.9 > 0.65
                    "timedOut": True,
                    "signalOwnedInterruption": False,
                    "timedOutDuringCompaction": False,
                    "timedOutDuringToolExecution": False,
                    "timedOutByRunBudget": False,
                    "state": {"timeoutCompactionAttempts": 0},
                }
            )
        )
        assert result is True
