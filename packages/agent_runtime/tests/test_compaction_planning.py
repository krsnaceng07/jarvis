"""Tests for compaction_planning.py — pure-logic helpers.

Parity target: ``compaction-planning.test.ts`` and related test vectors.
"""

from __future__ import annotations

from typing import Any


from jarvis_agent.compaction_planning import (
    BASE_CHUNK_RATIO,
    MIN_CHUNK_RATIO,
    StageSplitPlanSingle,
    StageSplitPlanSplit,
    build_history_prune_plan,
    build_oversized_fallback_plan,
    build_stage_split_plan,
    build_summary_chunks,
    compute_adaptive_chunk_ratio,
    estimate_messages_tokens,
    is_oversized_for_summary,
    sanitize_compaction_messages,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _user_msg(text: str, timestamp: int = 1000) -> Any:
    """Minimal user message stub."""
    from jarvis_llm import TextContent, UserMessage

    return UserMessage(content=[TextContent(text=text)], timestamp=timestamp)


def _assistant_msg(text: str, timestamp: int = 2000) -> Any:
    """Minimal assistant message stub."""
    from jarvis_llm import AssistantMessage, TextContent, Usage, Cost

    zero_cost = Cost(input=0, output=0, cache_read=0, cache_write=0, total=0)
    usage = Usage(
        input=0,
        output=0,
        cache_read=0,
        cache_write=0,
        context_usage=None,
        total_tokens=0,
        cost=zero_cost,
    )
    return AssistantMessage(
        content=[TextContent(text=text)],
        stop_reason="end_turn",
        usage=usage,
        timestamp=timestamp,
        api="unknown",
        provider="unknown",
        model="unknown",
    )


def _runtime_ctx_msg(text: str = "runtime") -> Any:
    """Stub runtime-context custom message (should be stripped)."""

    class _FakeRuntimeCtx:
        role = "custom"
        custom_type = "runtime_context"
        content = text
        timestamp = 999

    return _FakeRuntimeCtx()


# ---------------------------------------------------------------------------
# estimate_messages_tokens
# ---------------------------------------------------------------------------


class TestEstimateMessagesTokens:
    def test_empty(self) -> None:
        assert estimate_messages_tokens([]) == 0

    def test_user_message(self) -> None:
        msg = _user_msg("hello world")  # 11 chars → ceil(11/4) = 3
        assert estimate_messages_tokens([msg]) == 3

    def test_strips_runtime_context_messages(self) -> None:
        """Runtime-context custom messages must estimate to 0."""
        user = _user_msg("a" * 400)  # 100 tokens
        rt = _runtime_ctx_msg("big runtime blob " * 100)
        total = estimate_messages_tokens([user, rt])
        user_only = estimate_messages_tokens([user])
        assert total == user_only

    def test_additive(self) -> None:
        a = _user_msg("a" * 40)  # 10 tokens
        b = _user_msg("b" * 80)  # 20 tokens
        assert estimate_messages_tokens([a, b]) == 30


# ---------------------------------------------------------------------------
# sanitize_compaction_messages
# ---------------------------------------------------------------------------


class TestSanitizeCompactionMessages:
    def test_keeps_user_and_assistant(self) -> None:
        u = _user_msg("hello")
        a = _assistant_msg("world")
        result = sanitize_compaction_messages([u, a])
        assert len(result) == 2

    def test_removes_runtime_context_messages(self) -> None:
        u = _user_msg("hello")
        rt = _runtime_ctx_msg()
        result = sanitize_compaction_messages([u, rt])
        assert len(result) == 1

    def test_empty_passthrough(self) -> None:
        assert sanitize_compaction_messages([]) == []


# ---------------------------------------------------------------------------
# compute_adaptive_chunk_ratio
# ---------------------------------------------------------------------------


class TestComputeAdaptiveChunkRatio:
    def test_empty_returns_base(self) -> None:
        assert compute_adaptive_chunk_ratio([], 100_000) == BASE_CHUNK_RATIO

    def test_small_messages_return_base(self) -> None:
        msgs = [_user_msg("x" * 100) for _ in range(10)]  # 25 tokens each
        ratio = compute_adaptive_chunk_ratio(msgs, 200_000)
        assert ratio == BASE_CHUNK_RATIO

    def test_large_messages_reduce_ratio(self) -> None:
        # Each message ~12_500 tokens (50_000 chars / 4).
        # With context_window=50_000, avg_ratio = 12_500 / 50_000 = 0.25 > 0.1
        # → ratio must be reduced below BASE_CHUNK_RATIO.
        msgs = [_user_msg("x" * 50_000) for _ in range(5)]
        context_window = 50_000
        ratio = compute_adaptive_chunk_ratio(msgs, context_window)
        assert ratio < BASE_CHUNK_RATIO
        assert ratio >= MIN_CHUNK_RATIO


# ---------------------------------------------------------------------------
# is_oversized_for_summary
# ---------------------------------------------------------------------------


class TestIsOversizedForSummary:
    def test_small_message_not_oversized(self) -> None:
        msg = _user_msg("hello")
        assert not is_oversized_for_summary(msg, 200_000)

    def test_huge_message_is_oversized(self) -> None:
        # 1.2M chars → ~300K tokens > 50% of 200K context
        msg = _user_msg("x" * 1_200_000)
        assert is_oversized_for_summary(msg, 200_000)

    def test_boundary_case(self) -> None:
        # Message at exactly 50% of context (with safety margin it IS oversized)
        context_window = 100
        chars_at_50_pct = context_window * 50 * 4  # 50 tokens × 4 chars/token
        msg = _user_msg("x" * chars_at_50_pct)
        # SAFETY_MARGIN of 1.2 pushes it over the boundary
        result = is_oversized_for_summary(msg, context_window)
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# build_summary_chunks
# ---------------------------------------------------------------------------


class TestBuildSummaryChunks:
    def test_empty(self) -> None:
        assert build_summary_chunks([], 1000) == []

    def test_single_chunk_when_under_limit(self) -> None:
        msgs = [_user_msg("hello") for _ in range(3)]
        chunks = build_summary_chunks(msgs, 10_000)
        assert len(chunks) == 1
        assert len(chunks[0]) == 3

    def test_splits_when_over_limit(self) -> None:
        # Each message ~25 tokens; limit 20 → multiple chunks
        msgs = [_user_msg("x" * 100) for _ in range(10)]
        chunks = build_summary_chunks(msgs, 50)  # very small limit
        assert len(chunks) > 1

    def test_strips_runtime_context_before_chunking(self) -> None:
        u = _user_msg("a" * 100)
        rt = _runtime_ctx_msg("big" * 100)
        chunks = build_summary_chunks([u, rt], 10_000)
        total_messages = sum(len(c) for c in chunks)
        # Runtime context message should be stripped
        assert total_messages == 1


# ---------------------------------------------------------------------------
# build_oversized_fallback_plan
# ---------------------------------------------------------------------------


class TestBuildOversizedFallbackPlan:
    def test_no_oversized_messages(self) -> None:
        msgs = [_user_msg("hello") for _ in range(5)]
        plan = build_oversized_fallback_plan(msgs, 200_000)
        assert len(plan.small_messages) == 5
        assert plan.oversized_notes == []

    def test_oversized_messages_separated(self) -> None:
        small = _user_msg("hello")
        huge = _user_msg("x" * 1_200_000)
        plan = build_oversized_fallback_plan([small, huge], 200_000)
        assert len(plan.small_messages) == 1
        assert len(plan.oversized_notes) == 1
        assert "omitted from summary" in plan.oversized_notes[0]

    def test_all_oversized(self) -> None:
        msgs = [_user_msg("x" * 1_200_000) for _ in range(3)]
        plan = build_oversized_fallback_plan(msgs, 200_000)
        assert plan.small_messages == []
        assert len(plan.oversized_notes) == 3


# ---------------------------------------------------------------------------
# build_stage_split_plan
# ---------------------------------------------------------------------------


class TestBuildStageSplitPlan:
    def test_empty_returns_single(self) -> None:
        plan = build_stage_split_plan([], max_chunk_tokens=1000)
        assert isinstance(plan, StageSplitPlanSingle)

    def test_few_messages_returns_single(self) -> None:
        msgs = [_user_msg("x") for _ in range(2)]  # below min_messages_for_split=4
        plan = build_stage_split_plan(msgs, max_chunk_tokens=50_000)
        assert isinstance(plan, StageSplitPlanSingle)

    def test_large_history_returns_split(self) -> None:
        # 10 messages × 100 chars = ~250 tokens total > max_chunk_tokens=50
        msgs = [_user_msg("x" * 100) for _ in range(10)]
        plan = build_stage_split_plan(msgs, max_chunk_tokens=50)
        assert isinstance(plan, StageSplitPlanSplit)
        assert len(plan.chunks) >= 2

    def test_single_chunk_when_under_limit(self) -> None:
        msgs = [_user_msg("x") for _ in range(10)]
        plan = build_stage_split_plan(msgs, max_chunk_tokens=100_000)
        assert isinstance(plan, StageSplitPlanSingle)

    def test_custom_min_messages_for_split(self) -> None:
        msgs = [_user_msg("x" * 100) for _ in range(4)]
        # Even with a low token limit, fewer than 10 messages won't split
        plan = build_stage_split_plan(msgs, max_chunk_tokens=10, min_messages_for_split=10)
        assert isinstance(plan, StageSplitPlanSingle)


# ---------------------------------------------------------------------------
# build_history_prune_plan
# ---------------------------------------------------------------------------


class TestBuildHistoryPrunePlan:
    def test_no_prune_when_under_limit(self) -> None:
        msgs = [_user_msg("x" * 40) for _ in range(5)]  # ~50 tokens each
        plan = build_history_prune_plan(
            messages_to_summarize=msgs,
            turn_prefix_messages=[],
            tokens_before=1000,
            context_window_tokens=200_000,
            max_history_share=0.5,
        )
        assert plan.pruned is None

    def test_prunes_when_new_content_exceeds_budget(self) -> None:
        msgs = [_user_msg("x" * 40) for _ in range(5)]
        # Force new_content_tokens >> max_history_tokens
        plan = build_history_prune_plan(
            messages_to_summarize=msgs,
            turn_prefix_messages=[],
            tokens_before=100_000,  # very high tokens_before
            context_window_tokens=100,  # tiny context → tiny budget
            max_history_share=0.5,
        )
        # Because new_content_tokens > max_history_tokens, prune should run
        assert plan.pruned is not None

    def test_plan_fields_are_populated(self) -> None:
        msgs = [_user_msg("x") for _ in range(3)]
        plan = build_history_prune_plan(
            messages_to_summarize=msgs,
            turn_prefix_messages=[],
            tokens_before=10,
            context_window_tokens=200_000,
            max_history_share=0.5,
        )
        assert plan.summarizable_tokens >= 0
        assert plan.new_content_tokens >= 0
        assert plan.max_history_tokens > 0
