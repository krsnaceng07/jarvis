"""Phase 7.4b tests — tool-result-truncation."""
from __future__ import annotations



from src.agents.embedded_agent_runner.tool_result_truncation import (
    DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS,
    LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS,
    PROMPT_TOOL_RESULT_AGGREGATE_CAP_MULTIPLIER,
    XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS,
    calculate_max_tool_result_chars_with_cap,
    resolve_auto_live_tool_result_max_chars,
    resolve_live_tool_result_aggregate_max_chars,
    resolve_live_tool_result_max_chars,
    session_likely_has_oversized_tool_results,
    set_default_suffix_factory,
    set_resolve_configured_tool_result_max_chars_hook,
    truncate_oversized_tool_results_in_messages,
    truncate_tool_result_message,
)


def _install_default_hooks() -> None:
    set_resolve_configured_tool_result_max_chars_hook(lambda _cfg, _agent_id: None)
    set_default_suffix_factory(
        lambda truncated_chars: f"[... {max(1, int(truncated_chars))} chars truncated]"
    )


# ============================================================================
# resolve_auto_live_tool_result_max_chars
# ============================================================================


class TestResolveAutoLiveToolResultMaxChars:
    def test_default(self) -> None:
        assert (
            resolve_auto_live_tool_result_max_chars(0)
            == DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS
        )

    def test_non_finite(self) -> None:
        assert (
            resolve_auto_live_tool_result_max_chars(float("inf"))
            == DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS
        )
        assert (
            resolve_auto_live_tool_result_max_chars(float("nan"))
            == DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS
        )

    def test_large_context_tier(self) -> None:
        assert (
            resolve_auto_live_tool_result_max_chars(150_000)
            == LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS
        )

    def test_xl_context_tier(self) -> None:
        assert (
            resolve_auto_live_tool_result_max_chars(300_000)
            == XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS
        )

    def test_threshold_large(self) -> None:
        # Exactly at threshold.
        assert (
            resolve_auto_live_tool_result_max_chars(LARGE_CONTEXT_TOOL_RESULT_TOKENS := 100_000)
            == LARGE_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS
        )

    def test_threshold_xl(self) -> None:
        assert (
            resolve_auto_live_tool_result_max_chars(200_000)
            == XL_CONTEXT_MAX_LIVE_TOOL_RESULT_CHARS
        )


# ============================================================================
# calculate_max_tool_result_chars_with_cap
# ============================================================================


class TestCalculateMaxToolResultCharsWithCap:
    def test_basic(self) -> None:
        result = calculate_max_tool_result_chars_with_cap(10_000, 50_000)
        # maxTokens = 10000 * 0.5 = 5000; maxChars = 20000; min(20000, 50000) = 20000.
        assert result == 20_000

    def test_cap_below_max_chars(self) -> None:
        result = calculate_max_tool_result_chars_with_cap(10_000, 5_000)
        # maxTokens = 5000; maxChars = 20000; min(20000, 5000) = 5000.
        assert result == 5_000

    def test_cap_at_least_one(self) -> None:
        result = calculate_max_tool_result_chars_with_cap(10_000, 0)
        assert result >= 1

    def test_floor(self) -> None:
        result = calculate_max_tool_result_chars_with_cap(10_001, 100_000)
        # Should be a non-negative integer.
        assert isinstance(result, int)
        assert result >= 1


# ============================================================================
# resolve_live_tool_result_max_chars
# ============================================================================


class TestResolveLiveToolResultMaxChars:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_default_uses_auto(self) -> None:
        result = resolve_live_tool_result_max_chars(
            {"contextWindowTokens": 50_000}
        )
        assert result == DEFAULT_MAX_LIVE_TOOL_RESULT_CHARS

    def test_configured_cap_overrides(self) -> None:
        set_resolve_configured_tool_result_max_chars_hook(
            lambda _cfg, _agent_id: 8_000
        )
        try:
            result = resolve_live_tool_result_max_chars(
                {"contextWindowTokens": 50_000, "agentId": "a1"}
            )
            # 50000 * 0.5 * 4 = 100000; min(100000, 8000) = 8000.
            assert result == 8_000
        finally:
            set_resolve_configured_tool_result_max_chars_hook(
                lambda _cfg, _agent_id: None
            )


# ============================================================================
# resolve_live_tool_result_aggregate_max_chars
# ============================================================================


class TestResolveLiveToolResultAggregateMaxChars:
    def setup_method(self) -> None:
        _install_default_hooks()

    def test_basic(self) -> None:
        result = resolve_live_tool_result_aggregate_max_chars(
            {"contextWindowTokens": 50_000}
        )
        # perResultMax = 16000; aggregate = max(16000*4, 50000*4*0.5)
        # = max(64000, 100000) = 100000.
        assert result == 100_000

    def test_explicit_per_result(self) -> None:
        result = resolve_live_tool_result_aggregate_max_chars(
            {"contextWindowTokens": 10_000, "perResultMaxChars": 5_000}
        )
        # perResultMax = 5000; aggregate = max(5000*4, 10000*4*0.5)
        # = max(20000, 20000) = 20000.
        assert result == 20_000

    def test_per_result_dominates(self) -> None:
        result = resolve_live_tool_result_aggregate_max_chars(
            {"contextWindowTokens": 1_000, "perResultMaxChars": 50_000}
        )
        # perResultMax = 50000; aggregate = max(50000*4, 1000*4*0.5)
        # = max(200000, 2000) = 200000.
        assert result == 200_000

    def test_non_finite_context(self) -> None:
        result = resolve_live_tool_result_aggregate_max_chars(
            {"contextWindowTokens": float("inf"), "perResultMaxChars": 5_000}
        )
        # Falls back to 1 for non-finite.
        assert result >= 5_000 * PROMPT_TOOL_RESULT_AGGREGATE_CAP_MULTIPLIER


# ============================================================================
# truncate_tool_result_message
# ============================================================================


class TestTruncateToolResultMessage:
    def test_under_cap_unchanged(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "hello"}],
        }
        result = truncate_tool_result_message(msg, 100)
        assert result is msg

    def test_non_text_blocks_preserved(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [
                {"type": "image", "data": "x"},
                {"type": "text", "text": "x" * 5000},
            ],
        }
        result = truncate_tool_result_message(msg, 100)
        # Image block unchanged.
        assert result["content"][0] == {"type": "image", "data": "x"}

    def test_oversized_truncated(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "x" * 5000}],
        }
        result = truncate_tool_result_message(msg, 100)
        # The text block should be shorter than 5000 chars.
        new_text = result["content"][0]["text"]
        assert len(new_text) < 5000
        # Should contain the suffix.
        assert "truncated" in new_text

    def test_custom_suffix_string(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "x" * 5000}],
        }
        result = truncate_tool_result_message(
            msg, 100, {"suffix": "...CUSTOM..."}
        )
        assert "...CUSTOM..." in result["content"][0]["text"]

    def test_custom_suffix_callable(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "x" * 5000}],
        }
        result = truncate_tool_result_message(
            msg, 100, {"suffix": lambda n: f"<{n}>"}
        )
        assert "<" in result["content"][0]["text"]

    def test_string_content_preserved(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "x" * 5000, "content": "x" * 5000}],
        }
        result = truncate_tool_result_message(msg, 100)
        # Both text and content fields updated.
        assert len(result["content"][0]["text"]) < 5000
        assert len(result["content"][0]["content"]) < 5000

    def test_proportional_distribution(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [
                {"type": "text", "text": "a" * 2000},
                {"type": "text", "text": "b" * 2000},
            ],
        }
        result = truncate_tool_result_message(msg, 1000)
        # Each block should be truncated.
        assert len(result["content"][0]["text"]) < 2000
        assert len(result["content"][1]["text"]) < 2000

    def test_non_list_content(self) -> None:
        msg = {"role": "toolResult", "content": "raw string"}
        result = truncate_tool_result_message(msg, 100)
        # Non-list content returns the message unchanged.
        assert result is msg

    def test_non_dict_message(self) -> None:
        assert truncate_tool_result_message(None, 100) is None
        assert truncate_tool_result_message("string", 100) == "string"

    def test_min_keep_chars(self) -> None:
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "x" * 10000}],
        }
        result = truncate_tool_result_message(msg, 100, {"minKeepChars": 50})
        new_text = result["content"][0]["text"]
        # Result should be within block_budget.
        assert len(new_text) <= 100

    def test_min_keep_larger_than_max(self) -> None:
        # The effective min_keep is `min(minKeepChars, maxChars)` per
        # the OpenClaw source's `resolveEffectiveMinKeepChars`.
        # So min_keep of 10000 with max_chars 100 → effective 100.
        msg = {
            "role": "toolResult",
            "content": [{"type": "text", "text": "x" * 10000}],
        }
        result = truncate_tool_result_message(
            msg, 100, {"minKeepChars": 10_000}
        )
        new_text = result["content"][0]["text"]
        # Result is at most max_chars + suffix.
        assert len(new_text) <= 100 + len("[... 9999 chars truncated]")


# ============================================================================
# truncate_oversized_tool_results_in_messages
# ============================================================================


class TestTruncateOversizedToolResultsInMessages:
    def test_basic(self) -> None:
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "toolResult", "content": [{"type": "text", "text": "x" * 5000}]},
            {"role": "assistant", "content": "ok"},
        ]
        result = truncate_oversized_tool_results_in_messages(messages, 100)
        # Tool result should be truncated; user + assistant unchanged.
        assert result[0] == messages[0]
        assert result[1] is not messages[1]  # truncated
        assert len(result[1]["content"][0]["text"]) < 5000
        assert result[2] == messages[2]

    def test_under_cap_passes_through(self) -> None:
        messages = [
            {"role": "toolResult", "content": [{"type": "text", "text": "hi"}]},
        ]
        result = truncate_oversized_tool_results_in_messages(messages, 100)
        # Unchanged (same object).
        assert result[0] is messages[0]

    def test_non_tool_result_passes_through(self) -> None:
        messages = [
            {"role": "user", "content": [{"type": "text", "text": "x" * 5000}]},
        ]
        result = truncate_oversized_tool_results_in_messages(messages, 100)
        # User message is not touched.
        assert result[0] is messages[0]

    def test_non_dict_messages(self) -> None:
        messages = [None, "string", 42, {"role": "user", "content": "x"}]
        result = truncate_oversized_tool_results_in_messages(messages, 100)
        # Non-dict pass through.
        assert result[0] is None
        assert result[1] == "string"
        assert result[2] == 42
        assert result[3] == messages[3]

    def test_empty(self) -> None:
        assert truncate_oversized_tool_results_in_messages([], 100) == []


# ============================================================================
# session_likely_has_oversized_tool_results
# ============================================================================


class TestSessionLikelyHasOversizedToolResults:
    def test_no_tool_results(self) -> None:
        messages = [
            {"role": "user", "content": "x" * 5000},
            {"role": "assistant", "content": "x" * 5000},
        ]
        assert session_likely_has_oversized_tool_results(messages, 100) is False

    def test_under_cap(self) -> None:
        messages = [
            {"role": "toolResult", "content": [{"type": "text", "text": "hi"}]},
        ]
        assert session_likely_has_oversized_tool_results(messages, 100) is False

    def test_over_cap(self) -> None:
        messages = [
            {"role": "toolResult", "content": [{"type": "text", "text": "x" * 1000}]},
        ]
        assert session_likely_has_oversized_tool_results(messages, 100) is True

    def test_mixed(self) -> None:
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "toolResult", "content": [{"type": "text", "text": "x" * 1000}]},
            {"role": "assistant", "content": "ok"},
        ]
        assert session_likely_has_oversized_tool_results(messages, 100) is True

    def test_non_dict_messages_skipped(self) -> None:
        messages = [
            None,
            "string",
            42,
            {
                "role": "toolResult",
                "content": [{"type": "text", "text": "x" * 1000}],
            },
        ]
        assert session_likely_has_oversized_tool_results(messages, 100) is True
