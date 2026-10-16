"""Phase 5.8 gate: ``session_context.py`` against ``session-context.test.ts``.

The one vector OpenClaw ships (post-compaction replay) is ported verbatim as
:func:`test_replays_only_the_retained_tail_and_newer_entries_after_compaction`.
Everything else here covers branches that file never reaches.

The weight is on the compaction window. Every off-by-one in it silently
deletes real conversation turns from model context — the session tree still
looks correct on disk, and the only symptom is the model behaving as though
it forgot something.
"""

from __future__ import annotations

import pytest
from jarvis_llm.types import AssistantMessage, TextContent, UserMessage

from jarvis_agent.harness_types import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomEntry,
    CustomMessageEntry,
    LabelEntry,
    LeafEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionInfoEntry,
    SessionModelRef,
    SessionTreeEntry,
    ThinkingLevelChangeEntry,
)
from jarvis_agent.session_context import build_session_context

TIMESTAMP = "2026-07-17T00:00:00.000Z"
TIMESTAMP_MS = 1784246400000


def user_entry(entry_id: str, parent_id: str | None, content: str) -> SessionTreeEntry:
    """Mirror of the TS ``userEntry`` helper."""
    return MessageEntry(
        id=entry_id,
        parent_id=parent_id,
        timestamp=TIMESTAMP,
        message=UserMessage(content=content, timestamp=TIMESTAMP_MS),
    )


def roles(context: object) -> list[str]:
    return [m.role for m in context.messages]  # type: ignore[attr-defined]


def test_the_vector_timestamp_constant_is_right() -> None:
    """Guards the constant the rest of the file leans on.

    Asserted rather than trusted: a wrong TIMESTAMP_MS would make several
    tests below pass against the wrong expected value.
    """
    from jarvis_agent.messages import parse_session_timestamp_ms

    assert parse_session_timestamp_ms(TIMESTAMP) == TIMESTAMP_MS


# ── ported verbatim from session-context.test.ts ──────────────────────


def test_replays_only_the_retained_tail_and_newer_entries_after_compaction() -> None:
    entries: list[SessionTreeEntry] = [
        user_entry("old", None, "discarded"),
        user_entry("kept", "old", "retained"),
        ModelChangeEntry(
            id="model",
            parent_id="kept",
            timestamp=TIMESTAMP,
            provider="test-provider",
            model_id="test-model",
        ),
        CompactionEntry(
            id="compaction",
            parent_id="model",
            timestamp=TIMESTAMP,
            summary="older context",
            first_kept_entry_id="kept",
            tokens_before=123,
        ),
        user_entry("new", "compaction", "new turn"),
    ]

    context = build_session_context(entries)

    assert context.thinking_level == "off"
    assert context.model == SessionModelRef(provider="test-provider", model_id="test-model")
    assert roles(context) == ["compactionSummary", "user", "user"]
    assert context.messages[0].summary == "older context"
    assert context.messages[1].content == "retained"
    assert context.messages[2].content == "new turn"


# ── the compaction replay window ─────────────────────────────────────


def test_entries_before_the_first_kept_id_are_dropped() -> None:
    entries: list[SessionTreeEntry] = [
        user_entry("a", None, "drop-1"),
        user_entry("b", "a", "drop-2"),
        user_entry("c", "b", "keep-1"),
        user_entry("d", "c", "keep-2"),
        CompactionEntry(
            id="comp", timestamp=TIMESTAMP, summary="s", first_kept_entry_id="c", tokens_before=1
        ),
    ]
    contents = [m.content for m in build_session_context(entries).messages[1:]]
    assert contents == ["keep-1", "keep-2"]


def test_the_first_kept_entry_is_itself_included() -> None:
    """Inclusive lower bound.

    The flag is set *before* the append, so the boundary entry replays. A
    port that appended only after the flag was already set would lose one
    turn — the least visible possible off-by-one.
    """
    entries: list[SessionTreeEntry] = [
        user_entry("a", None, "dropped"),
        user_entry("boundary", "a", "boundary"),
        CompactionEntry(
            id="comp",
            timestamp=TIMESTAMP,
            summary="s",
            first_kept_entry_id="boundary",
            tokens_before=1,
        ),
    ]
    assert [m.content for m in build_session_context(entries).messages[1:]] == ["boundary"]


def test_a_first_kept_id_that_matches_nothing_drops_the_whole_prefix() -> None:
    """No match means the flag never flips, so nothing before replays.

    Entries *after* the compaction still replay — the bad id costs history,
    not the live turn.
    """
    entries: list[SessionTreeEntry] = [
        user_entry("a", None, "before"),
        CompactionEntry(
            id="comp",
            timestamp=TIMESTAMP,
            summary="s",
            first_kept_entry_id="ghost",
            tokens_before=1,
        ),
        user_entry("z", "comp", "after"),
    ]
    assert [m.content for m in build_session_context(entries).messages[1:]] == ["after"]


def test_entries_after_the_compaction_always_replay() -> None:
    """The regression the source comment warns about.

    If the post-compaction slice were dropped, every turn since the last
    compaction would vanish from context while remaining visible in the UI.
    """
    entries: list[SessionTreeEntry] = [
        CompactionEntry(
            id="comp", timestamp=TIMESTAMP, summary="s", first_kept_entry_id="none", tokens_before=1
        ),
        user_entry("x", "comp", "t1"),
        user_entry("y", "x", "t2"),
        user_entry("z", "y", "t3"),
    ]
    assert [m.content for m in build_session_context(entries).messages[1:]] == ["t1", "t2", "t3"]


def test_the_compaction_entry_itself_is_not_replayed_twice() -> None:
    """Exactly one summary message, from the synthetic prepend only."""
    entries: list[SessionTreeEntry] = [
        user_entry("a", None, "x"),
        CompactionEntry(
            id="comp", timestamp=TIMESTAMP, summary="s", first_kept_entry_id="a", tokens_before=1
        ),
    ]
    assert roles(build_session_context(entries)) == ["compactionSummary", "user"]


def test_the_summary_message_comes_first() -> None:
    """Order is load-bearing: the summary stands in for prior history."""
    entries: list[SessionTreeEntry] = [
        user_entry("a", None, "x"),
        CompactionEntry(
            id="comp", timestamp=TIMESTAMP, summary="s", first_kept_entry_id="a", tokens_before=1
        ),
        user_entry("b", "comp", "y"),
    ]
    assert roles(build_session_context(entries))[0] == "compactionSummary"


def test_the_last_compaction_wins() -> None:
    """Two compactions on one path: only the newest summary applies.

    Using the first would replay history the second one already discarded.
    """
    entries: list[SessionTreeEntry] = [
        user_entry("a", None, "gone"),
        CompactionEntry(
            id="c1", timestamp=TIMESTAMP, summary="first", first_kept_entry_id="a", tokens_before=1
        ),
        user_entry("b", "c1", "kept"),
        CompactionEntry(
            id="c2", timestamp=TIMESTAMP, summary="second", first_kept_entry_id="b", tokens_before=2
        ),
    ]
    context = build_session_context(entries)
    assert context.messages[0].summary == "second"
    assert [m.content for m in context.messages[1:]] == ["kept"]


def test_the_summary_carries_tokens_before_and_the_timestamp() -> None:
    entries: list[SessionTreeEntry] = [
        CompactionEntry(
            id="comp", timestamp=TIMESTAMP, summary="s", first_kept_entry_id="x", tokens_before=999
        )
    ]
    summary = build_session_context(entries).messages[0]
    assert summary.tokens_before == 999
    assert summary.timestamp == TIMESTAMP_MS


# ── the state scan ───────────────────────────────────────────────────


def test_the_last_thinking_level_change_wins() -> None:
    """Not the first.

    Breaking on the first match would pin the session to a stale level
    after the user changed it mid-conversation.
    """
    entries: list[SessionTreeEntry] = [
        ThinkingLevelChangeEntry(id="1", timestamp=TIMESTAMP, thinking_level="low"),
        ThinkingLevelChangeEntry(id="2", timestamp=TIMESTAMP, thinking_level="high"),
        ThinkingLevelChangeEntry(id="3", timestamp=TIMESTAMP, thinking_level="medium"),
    ]
    assert build_session_context(entries).thinking_level == "medium"


def test_thinking_level_defaults_to_off() -> None:
    """``"off"``, not ``None`` — an empty session has a concrete level."""
    assert build_session_context([]).thinking_level == "off"


def test_model_defaults_to_none() -> None:
    """Unlike thinking level, the model has no default and stays unset."""
    assert build_session_context([]).model is None


def test_an_assistant_message_counts_as_a_model_marker() -> None:
    """A resumed session with no explicit model_change still resolves."""
    entries: list[SessionTreeEntry] = [
        MessageEntry(
            id="1",
            timestamp=TIMESTAMP,
            message=AssistantMessage(
                api="anthropic-messages", provider="anthropic", model="claude-x"
            ),
        )
    ]
    assert build_session_context(entries).model == SessionModelRef(
        provider="anthropic", model_id="claude-x"
    )


def test_a_user_message_is_not_a_model_marker() -> None:
    """Only assistant messages carry provider identity."""
    assert build_session_context([user_entry("1", None, "hi")]).model is None


def test_a_later_assistant_message_overrides_an_earlier_model_change() -> None:
    """Ordering, not entry type, decides. The scan is a single pass."""
    entries: list[SessionTreeEntry] = [
        ModelChangeEntry(id="1", timestamp=TIMESTAMP, provider="p1", model_id="m1"),
        MessageEntry(
            id="2",
            timestamp=TIMESTAMP,
            message=AssistantMessage(api="anthropic-messages", provider="p2", model="m2"),
        ),
    ]
    assert build_session_context(entries).model == SessionModelRef(provider="p2", model_id="m2")


def test_a_later_model_change_overrides_an_earlier_assistant_message() -> None:
    """The converse — an explicit switch after a reply must take effect."""
    entries: list[SessionTreeEntry] = [
        MessageEntry(
            id="1",
            timestamp=TIMESTAMP,
            message=AssistantMessage(api="anthropic-messages", provider="p2", model="m2"),
        ),
        ModelChangeEntry(id="2", timestamp=TIMESTAMP, provider="p1", model_id="m1"),
    ]
    assert build_session_context(entries).model == SessionModelRef(provider="p1", model_id="m1")


def test_state_markers_are_scanned_across_the_compaction_boundary() -> None:
    """The scan runs over the full path, ignoring the replay window.

    A model set before the compaction still applies even though its entry
    is not replayed into messages — dropping it would silently fall back to
    the default model after every compaction.
    """
    entries: list[SessionTreeEntry] = [
        ModelChangeEntry(id="m", timestamp=TIMESTAMP, provider="early", model_id="early-model"),
        ThinkingLevelChangeEntry(id="t", timestamp=TIMESTAMP, thinking_level="high"),
        CompactionEntry(
            id="comp", timestamp=TIMESTAMP, summary="s", first_kept_entry_id="zzz", tokens_before=1
        ),
    ]
    context = build_session_context(entries)
    assert context.model == SessionModelRef(provider="early", model_id="early-model")
    assert context.thinking_level == "high"
    assert roles(context) == ["compactionSummary"]


# ── which entry types contribute messages ────────────────────────────


def test_bookkeeping_entries_contribute_no_messages() -> None:
    """These are session state, and must never reach the model.

    ``CustomEntry`` is the trap: it is one underscore away from
    ``CustomMessageEntry``, which *does* contribute. Leaking arbitrary
    application data into the prompt would be both a correctness and a
    privacy problem.
    """
    entries: list[SessionTreeEntry] = [
        CustomEntry(id="1", timestamp=TIMESTAMP, custom_type="t", data={"secret": True}),
        LabelEntry(id="2", timestamp=TIMESTAMP, target_id="1", label="x"),
        SessionInfoEntry(id="3", timestamp=TIMESTAMP, name="n"),
        LeafEntry(id="4", timestamp=TIMESTAMP, target_id="1"),
        ModelChangeEntry(id="5", timestamp=TIMESTAMP, provider="p", model_id="m"),
        ThinkingLevelChangeEntry(id="6", timestamp=TIMESTAMP, thinking_level="low"),
    ]
    assert build_session_context(entries).messages == []


def test_a_custom_message_entry_becomes_a_custom_message() -> None:
    entries: list[SessionTreeEntry] = [
        CustomMessageEntry(
            id="1",
            timestamp=TIMESTAMP,
            custom_type="note",
            content="visible",
            display=True,
            details={"source": "test"},
        )
    ]
    message = build_session_context(entries).messages[0]
    assert message.role == "custom"
    assert message.custom_type == "note"
    assert message.content == "visible"
    assert message.timestamp == TIMESTAMP_MS


def test_a_custom_message_entry_keeps_block_content() -> None:
    blocks = [TextContent(text="a"), TextContent(text="b")]
    entries: list[SessionTreeEntry] = [
        CustomMessageEntry(id="1", timestamp=TIMESTAMP, custom_type="t", content=blocks)
    ]
    assert build_session_context(entries).messages[0].content == blocks


def test_a_branch_summary_entry_becomes_a_branch_summary_message() -> None:
    entries: list[SessionTreeEntry] = [
        BranchSummaryEntry(id="1", timestamp=TIMESTAMP, from_id="other", summary="what happened")
    ]
    message = build_session_context(entries).messages[0]
    assert message.role == "branchSummary"
    assert message.summary == "what happened"
    assert message.from_id == "other"


@pytest.mark.parametrize("summary", ["", None])
def test_an_empty_branch_summary_is_skipped(summary: str | None) -> None:
    """Falsy summary means no message, not empty framing.

    Empty framing would tell the model a branch occurred while conveying
    nothing about it — worse than silence.
    """
    entries: list[SessionTreeEntry] = [
        BranchSummaryEntry(id="1", timestamp=TIMESTAMP, from_id="o", summary=summary)  # type: ignore[arg-type]
    ]
    assert build_session_context(entries).messages == []


def test_provider_messages_pass_through_by_identity() -> None:
    """Not copied — the same object the session stored."""
    message = UserMessage(content="hi", timestamp=TIMESTAMP_MS)
    entries: list[SessionTreeEntry] = [MessageEntry(id="1", timestamp=TIMESTAMP, message=message)]
    assert build_session_context(entries).messages[0] is message


def test_a_message_entry_with_no_message_is_skipped() -> None:
    """Defensive: ``message`` is Optional only because the dataclass needs
    a default. A malformed persisted row must not crash session load."""
    entries: list[SessionTreeEntry] = [MessageEntry(id="1", timestamp=TIMESTAMP, message=None)]
    assert build_session_context(entries).messages == []


def test_message_order_follows_path_order() -> None:
    entries: list[SessionTreeEntry] = [
        user_entry("1", None, "one"),
        user_entry("2", "1", "two"),
        user_entry("3", "2", "three"),
    ]
    assert [m.content for m in build_session_context(entries).messages] == ["one", "two", "three"]


def test_an_empty_path_yields_an_empty_context() -> None:
    context = build_session_context([])
    assert context.messages == []
    assert context.thinking_level == "off"
    assert context.model is None
