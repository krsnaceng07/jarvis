"""Phase 5.10 test vectors: compaction + branch summarization.

Ports, in order:
- ``harness/compaction/utils.test.ts`` (serializeConversation vectors)
- ``harness/compaction/compaction-image-tokens.test.ts``
- ``harness/compaction/compaction-trailing-toolresult.test.ts``
- ``harness/compaction/compaction.test.ts``

Fixture builders mirror the upstream files' local helpers. Entry ids follow
the upstream ``entry-{index}`` convention so index assertions read the same.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from jarvis_llm import (
    AssistantMessage,
    ContextUsageAvailable,
    ContextUsageUnavailable,
    Cost,
    ImageContent,
    Model,
    ModelCost,
    TextContent,
    ToolResultMessage,
    Usage,
    UserMessage,
)
from jarvis_llm.event_stream import AssistantMessageEventStream

from jarvis_agent import (
    CompactionSettings,
    MessageEntry,
    calculate_context_tokens,
    compact,
    estimate_context_tokens,
    estimate_tokens,
    find_cut_point,
    generate_summary,
    get_last_assistant_usage,
    prepare_compaction,
    serialize_conversation,
)
from jarvis_agent.compaction import CompactionPreparation
from jarvis_agent.compaction_utils import create_file_ops
from jarvis_agent.harness_types import (
    BranchSummaryEntry,
    CustomMessageEntry,
    SessionTreeEntry,
)


def _zero_cost() -> Cost:
    return Cost(input=0, output=0, cache_read=0, cache_write=0, total=0)


def _usage(
    total_tokens: int = 0,
    *,
    input: int = 0,
    output: int = 0,
    cache_read: int = 0,
    cache_write: int = 0,
    context_usage: Any = None,
) -> Usage:
    return Usage(
        input=input,
        output=output,
        cache_read=cache_read,
        cache_write=cache_write,
        context_usage=context_usage,
        total_tokens=total_tokens,
        cost=_zero_cost(),
    )


def create_usage(total_tokens: int) -> Usage:
    """Parity: compaction.test.ts ``createUsage``."""
    return _usage(
        total_tokens,
        input=total_tokens,
        context_usage=ContextUsageAvailable(prompt_tokens=total_tokens, total_tokens=total_tokens),
    )


def create_assistant(
    text: str,
    usage: Usage,
    timestamp: int,
    *,
    api: str = "test-api",
    provider: str = "test-provider",
    model: str = "test-model",
    stop_reason: str = "stop",
) -> AssistantMessage:
    """Parity: compaction.test.ts ``createAssistant``."""
    return AssistantMessage(
        role="assistant",
        content=[TextContent(text=text)],
        api=api,
        provider=provider,
        model=model,
        usage=usage,
        stop_reason=stop_reason,
        timestamp=timestamp,
    )


def assistant_text(text: str, timestamp: int) -> AssistantMessage:
    """Parity: the zero-usage ``assistantText`` used by the image/tool tests."""
    return create_assistant(
        text,
        _usage(0),
        timestamp,
        api="anthropic-messages",
        provider="anthropic",
        model="claude-fable-5",
    )


def user_text(text: str, timestamp: int) -> UserMessage:
    return UserMessage(content=[TextContent(text=text)], timestamp=timestamp)


def message_entry(message: Any, index: int) -> MessageEntry:
    """Parity: ``messageEntry`` / ``createMessageEntry``."""
    return MessageEntry(
        id=f"entry-{index}",
        parent_id=None if index == 0 else f"entry-{index - 1}",
        timestamp="1970-01-01T00:00:00.000Z",
        message=message,
    )


def projected_entry(entry_type: str, index: int, content: str) -> SessionTreeEntry:
    """Parity: compaction.test.ts ``createProjectedEntry``."""
    parent_id = None if index == 0 else f"entry-{index - 1}"
    common = {
        "id": f"entry-{index}",
        "parent_id": parent_id,
        "timestamp": "1970-01-01T00:00:00.000Z",
    }
    if entry_type == "custom_message":
        return CustomMessageEntry(custom_type="test", content=content, display=True, **common)
    return BranchSummaryEntry(from_id=parent_id or common["id"], summary=content, **common)


def make_model(**overrides: Any) -> Model:
    base = dict(
        id="summary-model",
        name="Summary Model",
        api="test-api",
        provider="test-provider",
        base_url="https://example.test",
        reasoning=False,
        input=["text"],
        cost=ModelCost(input=0, output=0, cache_read=0, cache_write=0),
        context_window=100_000,
        max_tokens=8_000,
    )
    base.update(overrides)
    return Model(**base)


def summary_stream(message: AssistantMessage) -> AssistantMessageEventStream:
    from jarvis_llm import StreamEventDone

    stream = AssistantMessageEventStream()
    stream.push(StreamEventDone(reason="stop", message=message))
    stream.end()
    return stream


# ── utils.test.ts: serializeConversation ─────────────────────────────


class TestSerializeConversation:
    @pytest.mark.parametrize(
        "block, expected",
        [
            (
                {
                    "type": "toolResult",
                    "id": "call-1",
                    "toolUseId": "call-1",
                    "content": "duplicate fallback",
                    "text": "codex nested output",
                },
                "codex nested output",
            ),
            (
                {"type": "tool_result", "content": "fallback output"},
                "fallback output",
            ),
        ],
    )
    def test_serializes_nested_tool_result_blocks(self, block, expected):
        messages = [ToolResultMessage(tool_call_id="call-1", tool_name="t", content=[block])]

        assert serialize_conversation(messages) == f"[Tool result]: {expected}"

    def test_keeps_truncated_tool_results_utf16_safe_with_exact_omitted_count(self):
        prefix = "a" * 1_999
        messages = [
            ToolResultMessage(
                tool_call_id="call-1",
                tool_name="t",
                content=[{"type": "toolResult", "content": f"{prefix}\U0001f680tail"}],
            )
        ]

        assert serialize_conversation(messages) == (
            f"[Tool result]: {prefix}\n\n[... 6 more characters truncated]"
        )


# ── compaction-image-tokens.test.ts ──────────────────────────────────

IMAGE_PAYLOAD = "a" * 1_500_000


def image_block() -> ImageContent:
    return ImageContent(data=IMAGE_PAYLOAD, mime_type="image/png")


def user_image(timestamp: int) -> UserMessage:
    return UserMessage(content=[image_block()], timestamp=timestamp)


def tool_result_image(timestamp: int) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id="call-1",
        tool_name="screenshot",
        content=[image_block()],
        is_error=False,
        timestamp=timestamp,
    )


def build_image_transcript(recent_user_turns: list) -> list[SessionTreeEntry]:
    """Parity: compaction-image-tokens.test.ts ``buildTranscript``."""
    messages: list[Any] = [user_text("start of the conversation", 1)]
    timestamp = 2
    for turn in recent_user_turns:
        messages.append(assistant_text("ok", timestamp))
        timestamp += 1
        messages.append(turn)
    return [message_entry(message, index) for index, message in enumerate(messages)]


class TestEstimateTokensImageAccounting:
    def test_charges_user_image_same_as_tool_result_image(self):
        user_tokens = estimate_tokens(user_image(1))
        tool_tokens = estimate_tokens(tool_result_image(1))

        assert user_tokens == tool_tokens
        assert user_tokens >= 1200


class TestFindCutPointWithImageHeavyRecentTurns:
    def test_trims_image_dominated_user_turns(self):
        entries = build_image_transcript([user_image(10), user_image(20), user_image(30)])

        result = find_cut_point(entries, 0, len(entries), 1500)

        assert result.first_kept_entry_index > 0

    def test_matches_cut_point_of_equivalent_text_cost_control(self):
        equivalent_text = "x" * 4800
        image_entries = build_image_transcript([user_image(10), user_image(20), user_image(30)])
        text_entries = build_image_transcript(
            [
                user_text(equivalent_text, 10),
                user_text(equivalent_text, 20),
                user_text(equivalent_text, 30),
            ]
        )

        image_result = find_cut_point(image_entries, 0, len(image_entries), 1500)
        text_result = find_cut_point(text_entries, 0, len(text_entries), 1500)

        assert text_result.first_kept_entry_index > 0
        assert image_result.first_kept_entry_index == text_result.first_kept_entry_index


# ── compaction-trailing-toolresult.test.ts ───────────────────────────

KEEP_RECENT_TOKENS = 20000
LARGE_TOOL_OUTPUT = "x" * 120000


def tool_result_text(text: str, timestamp: int) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id="call-1",
        tool_name="bash",
        content=[TextContent(text=text)],
        is_error=False,
        timestamp=timestamp,
    )


def nested_tool_result(block: dict, timestamp: int) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id="call-1",
        tool_name="codex_progress",
        content=[{"id": "call-1", "toolUseId": "call-1", **block}],
        is_error=False,
        timestamp=timestamp,
    )


def build_tool_result_transcript(tool_result: ToolResultMessage) -> list[SessionTreeEntry]:
    """Parity: compaction-trailing-toolresult.test.ts ``buildTranscriptWithToolResult``."""
    messages = [
        user_text("start of the conversation", 1),
        assistant_text("first reply", 2),
        user_text("please run the command", 3),
        assistant_text("running it now", 4),
        tool_result,
    ]
    return [message_entry(message, index) for index, message in enumerate(messages)]


class TestFindCutPointWithTrailingOversizedToolResult:
    def test_counts_final_tool_result_as_larger_than_keep_budget(self):
        trailing = tool_result_text(LARGE_TOOL_OUTPUT, 5)

        assert estimate_tokens(trailing) >= KEEP_RECENT_TOKENS

    def test_trims_prefix_instead_of_keeping_whole_transcript(self):
        entries = build_tool_result_transcript(tool_result_text(LARGE_TOOL_OUTPUT, 5))

        result = find_cut_point(entries, 0, len(entries), KEEP_RECENT_TOKENS)

        assert result.first_kept_entry_index > 0
        assert result.first_kept_entry_index == 3

    @pytest.mark.parametrize(
        "block",
        [
            {"type": "toolResult", "content": "duplicate", "text": LARGE_TOOL_OUTPUT},
            {"type": "tool_result", "content": LARGE_TOOL_OUTPUT},
        ],
    )
    def test_counts_and_trims_prefix_for_nested_tool_result_shapes(self, block):
        trailing = nested_tool_result(block, 5)
        entries = build_tool_result_transcript(trailing)

        assert estimate_tokens(trailing) >= KEEP_RECENT_TOKENS
        result = find_cut_point(entries, 0, len(entries), KEEP_RECENT_TOKENS)

        assert result.first_kept_entry_index > 0
        assert result.first_kept_entry_index == 3


# ── compaction.test.ts: calculateContextTokens ───────────────────────


class TestCalculateContextTokens:
    def test_prefers_final_iteration_context_snapshot_over_aggregate_billing(self):
        assert (
            calculate_context_tokens(
                _usage(
                    927_907,
                    input=12,
                    output=15_104,
                    cache_read=819_661,
                    cache_write=93_130,
                    context_usage=ContextUsageAvailable(
                        prompt_tokens=148_874, total_tokens=163_978
                    ),
                )
            )
            == 163_978
        )

    def test_preserves_numeric_compatibility_fallback_when_snapshot_unavailable(self):
        assert (
            calculate_context_tokens(
                _usage(
                    927_907,
                    input=12,
                    output=15_104,
                    cache_read=819_661,
                    cache_write=93_130,
                    context_usage=ContextUsageUnavailable(),
                )
            )
            == 927_907
        )

    def test_estimates_transcript_when_context_unavailable(self):
        estimate = estimate_context_tokens(
            [
                UserMessage(content="hello", timestamp=0),
                create_assistant(
                    "done",
                    _usage(
                        927_907,
                        input=12,
                        output=15_104,
                        cache_read=819_661,
                        cache_write=93_130,
                        context_usage=ContextUsageUnavailable(),
                    ),
                    1,
                    api="anthropic-messages",
                    provider="anthropic",
                    model="claude-fable-5",
                ),
            ]
        )

        assert estimate.tokens < 927_907
        assert estimate.tokens > 0
        assert estimate.usage_tokens == 0
        assert estimate.last_usage_index is None

    def test_uses_previous_exact_snapshot_and_estimates_only_unavailable_tail(self):
        estimate = estimate_context_tokens(
            [
                create_assistant(
                    "previous",
                    _usage(
                        149_874,
                        input=12,
                        output=1_000,
                        cache_read=148_862,
                        context_usage=ContextUsageAvailable(
                            prompt_tokens=148_874, total_tokens=149_874
                        ),
                    ),
                    0,
                    api="anthropic-messages",
                    provider="anthropic",
                    model="claude-fable-5",
                ),
                UserMessage(content="next", timestamp=1),
                create_assistant(
                    "done",
                    _usage(
                        927_907,
                        input=12,
                        output=15_104,
                        cache_read=819_661,
                        cache_write=93_130,
                        context_usage=ContextUsageUnavailable(),
                    ),
                    2,
                    api="anthropic-messages",
                    provider="anthropic",
                    model="claude-fable-5",
                ),
            ]
        )

        assert estimate.usage_tokens == 149_874
        assert estimate.tokens > 149_874
        assert estimate.tokens < 927_907
        assert estimate.last_usage_index == 0

    def test_ignores_all_zero_terminal_usage_block(self):
        valid_usage = create_usage(20)
        messages = [
            create_assistant("complete", valid_usage, 1),
            UserMessage(content="continue", timestamp=2),
            create_assistant("partial", create_usage(0), 3),
        ]
        entries = [message_entry(message, index) for index, message in enumerate(messages)]

        assert get_last_assistant_usage(entries) is valid_usage
        estimate = estimate_context_tokens(messages)
        assert estimate.usage_tokens == 20
        assert estimate.last_usage_index == 0
        assert estimate.trailing_tokens > 0


# ── compaction.test.ts: session-entry compaction budgeting ───────────


class TestSessionEntryCompactionBudgeting:
    @pytest.mark.parametrize("entry_type", ["custom_message", "branch_summary"])
    def test_counts_projected_entry_in_model_context(self, entry_type):
        entries = [
            message_entry(UserMessage(content="hi", timestamp=1), 0),
            message_entry(create_assistant("hello", create_usage(2), 2), 1),
            projected_entry(entry_type, 2, "x" * 4_000),
            message_entry(create_assistant("ok", create_usage(2), 4), 3),
        ]

        split = find_cut_point(entries, 0, len(entries), 1)
        assert split.first_kept_entry_index == 3
        assert split.turn_start_index == 2
        assert split.is_split_turn is True

        whole = find_cut_point(entries, 0, len(entries), 2)
        assert whole.first_kept_entry_index == 2
        assert whole.turn_start_index == -1
        assert whole.is_split_turn is False

    @pytest.mark.parametrize("entry_type", ["custom_message", "branch_summary"])
    def test_does_not_rewind_across_adjacent_projected_entries(self, entry_type):
        entries = [
            message_entry(UserMessage(content="hi", timestamp=1), 0),
            message_entry(create_assistant("hello", create_usage(2), 2), 1),
            projected_entry(entry_type, 2, "x" * 4_000),
            projected_entry(entry_type, 3, "y" * 4_000),
            message_entry(create_assistant("ok", create_usage(2), 5), 4),
        ]

        result = find_cut_point(entries, 0, len(entries), 2)
        assert result.first_kept_entry_index == 3
        assert result.turn_start_index == -1
        assert result.is_split_turn is False

    def test_skips_compaction_when_nothing_would_be_summarized(self):
        entries = [
            message_entry(UserMessage(content="hello", timestamp=1), 0),
            message_entry(create_assistant("done", create_usage(2), 2), 1),
        ]

        result = prepare_compaction(
            entries,
            CompactionSettings(enabled=True, reserve_tokens=0, keep_recent_tokens=10_000),
        )
        assert result.ok is True
        assert result.value is None


# ── compaction.test.ts: generateSummary thinking options ─────────────


class TestGenerateSummaryThinkingOptions:
    def test_maps_explicit_fable_off_to_low_effort_for_compaction(self):
        model = make_model(
            id="production-fable",
            name="Production Fable",
            api="anthropic-messages",
            provider="anthropic",
            base_url="https://api.anthropic.com",
            context_window=1_000_000,
            max_tokens=128_000,
            params={"canonicalModelId": "claude-fable-5"},
            thinking_level_map={"off": "low"},
        )
        summary_message = create_assistant(
            "summary",
            _usage(0),
            1,
            api=model.api,
            provider=model.provider,
            model=model.id,
        )
        calls: list[Any] = []

        def stream_fn(stream_model, context, options):
            calls.append(options)
            assert options.reasoning == "low"
            assert "user and an AI assistant" in context.system_prompt
            assert "AI coding assistant" not in context.system_prompt
            return summary_stream(summary_message)

        result = asyncio.run(
            generate_summary(
                [UserMessage(content="hello", timestamp=1)],
                model,
                1000,
                None,
                None,
                None,
                None,
                None,
                "off",
                stream_fn,
            )
        )

        assert result.ok is True
        assert result.value == "summary"
        assert len(calls) == 1


# ── compaction.test.ts: split-turn compaction ────────────────────────


class TestSplitTurnCompaction:
    def test_serializes_history_and_turn_prefix_summaries(self):
        model = make_model()
        state = {"active": 0, "max_active": 0, "call_count": 0}

        def stream_fn(stream_model, context, options):
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            state["call_count"] += 1
            call_number = state["call_count"]
            stream = AssistantMessageEventStream()

            async def finish() -> None:
                from jarvis_llm import StreamEventDone

                await asyncio.sleep(0.005)
                state["active"] -= 1
                message = create_assistant(
                    f"summary-{call_number}",
                    _usage(0),
                    1,
                    api=model.api,
                    provider=model.provider,
                    model=model.id,
                )
                stream.push(StreamEventDone(reason="stop", message=message))
                stream.end()

            asyncio.ensure_future(finish())
            return stream

        async def run():
            return await compact(
                CompactionPreparation(
                    first_kept_entry_id="kept-entry",
                    messages_to_summarize=[UserMessage(content="history", timestamp=1)],
                    turn_prefix_messages=[UserMessage(content="prefix", timestamp=2)],
                    is_split_turn=True,
                    tokens_before=100,
                    file_ops=create_file_ops(),
                    settings=CompactionSettings(
                        enabled=True, reserve_tokens=1_000, keep_recent_tokens=100
                    ),
                ),
                model,
                None,
                None,
                None,
                None,
                None,
                stream_fn,
            )

        result = asyncio.run(run())

        assert result.ok is True
        assert state["call_count"] == 2
        assert state["max_active"] == 1
