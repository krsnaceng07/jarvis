"""Phase 5.8 gate: ``messages.py`` against ``messages.test.ts``.

All four cases from ``packages/agent-core/src/harness/messages.test.ts``
(69 lines) are ported verbatim, plus the branches that file does not reach:
the bash renderer's mutually-exclusive cancelled/exit-code arms, the
exclude-from-context drop, the summary framing text, and passthrough.

The two cases that matter most are the timestamp pair. Writing a bad
timestamp must raise; reading one must not. Getting the second wrong makes a
single corrupt persisted row render the whole session unloadable — a failure
that only shows up on real user data, long after shipping.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from jarvis_llm.types import AssistantMessage, TextContent, UserMessage

from jarvis_agent.messages import (
    BRANCH_SUMMARY_PREFIX,
    BRANCH_SUMMARY_SUFFIX,
    COMPACTION_SUMMARY_PREFIX,
    COMPACTION_SUMMARY_SUFFIX,
    as_agent_message,
    bash_execution_to_text,
    convert_to_llm,
    create_branch_summary_message,
    create_compaction_summary_message,
    create_custom_message,
    normalize_compaction_summary_timestamp,
    parse_session_timestamp_ms,
    require_session_timestamp_ms,
)
from jarvis_agent.types import (
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)

TIMESTAMP = "2026-05-30T17:00:00.000Z"


def _date_parse(value: str) -> int:
    """Reference implementation of ``Date.parse`` for the vectors below."""
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    return int(datetime.fromisoformat(text).timestamp() * 1000)


def _text_of(message: Any) -> str:
    assert isinstance(message.content, list)
    block = message.content[0]
    assert isinstance(block, TextContent)
    return block.text


# ── ported verbatim from messages.test.ts ────────────────────────────


def test_rejects_invalid_timestamps_before_creating_context_messages() -> None:
    """Vector: ``createCustomMessage(..., "not-a-date")`` throws.

    The message text is asserted because the TS test asserts it; a port
    that raised a different message would pass a weaker check.
    """
    with pytest.raises(ValueError) as excinfo:
        create_custom_message("note", "content", True, {}, "not-a-date")
    assert "custom message timestamp must be a valid timestamp" in str(excinfo.value)


def test_normalizes_persisted_compaction_summary_timestamp_strings() -> None:
    """Vector: a persisted ISO string becomes ``Date.parse(timestamp)``."""
    persisted = [
        CompactionSummaryMessage(summary="older context", tokens_before=123, timestamp=TIMESTAMP)
    ]
    message = convert_to_llm(persisted)[0]
    assert message.timestamp == _date_parse(TIMESTAMP)


def test_keeps_corrupt_persisted_compaction_timestamps_non_fatal() -> None:
    """Vector: ``timestamp: "not a timestamp"`` yields ``0``, not an error.

    This is the case that protects real sessions. Raising here would make
    one bad row unload an entire conversation.
    """
    persisted = [
        CompactionSummaryMessage(
            summary="older context", tokens_before=123, timestamp="not a timestamp"
        )
    ]
    message = convert_to_llm(persisted)[0]
    assert message.timestamp == 0


def test_marks_a_runtime_context_carrier_custom_message() -> None:
    """Vector: providers must skip cache anchoring on this message."""
    message = convert_to_llm(
        [
            create_custom_message(
                "openclaw.runtime-context",
                "current-turn metadata",
                False,
                {"source": "openclaw-runtime-context", "runtimeContextCarrier": True},
                TIMESTAMP,
            )
        ]
    )[0]
    assert message.role == "user"
    assert message.runtime_context_carrier is True


def test_does_not_mark_ordinary_custom_messages() -> None:
    """Vector: the field is *absent*, not False.

    ``to_dict`` omits ``None``, so the serialized message has no
    ``runtimeContextCarrier`` key at all — matching the TS conditional
    spread rather than emitting ``false``.
    """
    message = convert_to_llm(
        [create_custom_message("note", "some note", False, {"source": "other"}, TIMESTAMP)]
    )[0]
    assert message.role == "user"
    assert message.runtime_context_carrier is None
    assert "runtimeContextCarrier" not in message.to_dict()


# ── the carrier check is strict ──────────────────────────────────────


@pytest.mark.parametrize(
    "details",
    [
        {"runtimeContextCarrier": "yes"},
        {"runtimeContextCarrier": 1},
        {"runtimeContextCarrier": False},
        {"runtimeContextCarrier": None},
        {},
        None,
        "not a mapping",
    ],
)
def test_only_exactly_true_marks_a_carrier(details: Any) -> None:
    """``=== true``, not truthiness.

    ``details`` is opaque application data that round-trips through JSON.
    A truthy ``1`` treated as a carrier would disable prompt-cache anchoring
    for the conversation — a silent, expensive regression.
    """
    message = convert_to_llm([create_custom_message("note", "x", False, details, TIMESTAMP)])[0]
    assert message.runtime_context_carrier is None


# ── timestamp helpers ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (TIMESTAMP, _date_parse(TIMESTAMP)),
        ("2026-05-30T17:00:00.000+00:00", _date_parse(TIMESTAMP)),
        # Whitespace is trimmed before parsing.
        (f"  {TIMESTAMP}  ", _date_parse(TIMESTAMP)),
        ("not a timestamp", None),
        ("", None),
        ("   ", None),
        (None, None),
        (123, None),
        (True, None),
    ],
)
def test_parse_session_timestamp_ms(value: Any, expected: int | None) -> None:
    """Parity: ``parseSessionTimestampMs``, including the non-string guard."""
    assert parse_session_timestamp_ms(value) == expected


def test_require_and_parse_differ_only_in_failure_mode() -> None:
    """Same success value; one raises where the other returns ``None``.

    That asymmetry is the design: strict when a caller can still be blamed,
    lenient when the data is already on disk.
    """
    assert require_session_timestamp_ms(TIMESTAMP, "x") == parse_session_timestamp_ms(TIMESTAMP)
    with pytest.raises(ValueError):
        require_session_timestamp_ms("bad", "x")
    assert parse_session_timestamp_ms("bad") is None


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        (1234, 1234),
        (0, 0),
        (TIMESTAMP, _date_parse(TIMESTAMP)),
        ("garbage", 0),
        ("", 0),
        # `isinstance(True, int)` is True in Python, so a stray boolean
        # would otherwise become a timestamp of 1.
        (True, 0),
        (False, 0),
    ],
)
def test_normalize_compaction_summary_timestamp(timestamp: Any, expected: int) -> None:
    assert normalize_compaction_summary_timestamp(timestamp) == expected


@pytest.mark.parametrize(
    ("factory", "label"),
    [
        (lambda ts: create_branch_summary_message("s", "from", ts), "branch summary timestamp"),
        (lambda ts: create_compaction_summary_message("s", 1, ts), "compaction summary timestamp"),
        (lambda ts: create_custom_message("t", "c", True, None, ts), "custom message timestamp"),
    ],
)
def test_every_constructor_is_strict_about_timestamps(factory: Any, label: str) -> None:
    """All three constructors raise, each with its own label."""
    with pytest.raises(ValueError) as excinfo:
        factory("nope")
    assert f"{label} must be a valid timestamp" in str(excinfo.value)
    assert factory(TIMESTAMP).timestamp == _date_parse(TIMESTAMP)


# ── bash rendering ───────────────────────────────────────────────────


def test_bash_with_output_is_fenced() -> None:
    text = bash_execution_to_text(
        BashExecutionMessage(command="ls", output="a\nb", exit_code=0, timestamp=1)
    )
    assert text == "Ran `ls`\n```\na\nb\n```"


def test_bash_without_output_says_no_output() -> None:
    text = bash_execution_to_text(BashExecutionMessage(command="true", output="", timestamp=1))
    assert text == "Ran `true`\n(no output)"


def test_zero_exit_code_adds_no_line() -> None:
    """``0`` is success. The check is explicit, not a truthiness test."""
    text = bash_execution_to_text(
        BashExecutionMessage(command="true", output="ok", exit_code=0, timestamp=1)
    )
    assert "exited with code" not in text


def test_missing_exit_code_adds_no_line() -> None:
    text = bash_execution_to_text(
        BashExecutionMessage(command="x", output="ok", exit_code=None, timestamp=1)
    )
    assert "exited with code" not in text


def test_nonzero_exit_code_is_reported() -> None:
    text = bash_execution_to_text(
        BashExecutionMessage(command="false", output="", exit_code=1, timestamp=1)
    )
    assert text.endswith("\n\nCommand exited with code 1")


def test_cancelled_suppresses_the_exit_code_line() -> None:
    """``else if``: the two branches are mutually exclusive.

    An interrupted process's exit code is misleading, so a cancelled
    command reports only cancellation. A port using two ``if``s would emit
    both lines.
    """
    text = bash_execution_to_text(
        BashExecutionMessage(command="sleep", output="", exit_code=130, cancelled=True, timestamp=1)
    )
    assert text.endswith("\n\n(command cancelled)")
    assert "exited with code" not in text


def test_truncation_note_requires_both_flag_and_path() -> None:
    both = bash_execution_to_text(
        BashExecutionMessage(
            command="cat", output="x", truncated=True, full_output_path="/tmp/o", timestamp=1
        )
    )
    assert both.endswith("\n\n[Output truncated. Full output: /tmp/o]")

    no_path = bash_execution_to_text(
        BashExecutionMessage(command="cat", output="x", truncated=True, timestamp=1)
    )
    assert "Output truncated" not in no_path

    no_flag = bash_execution_to_text(
        BashExecutionMessage(command="cat", output="x", full_output_path="/tmp/o", timestamp=1)
    )
    assert "Output truncated" not in no_flag


# ── convert_to_llm branches ──────────────────────────────────────────


def test_exclude_from_context_drops_the_message() -> None:
    """Kept in session history, hidden from the model."""
    messages = [
        BashExecutionMessage(command="secret", output="x", timestamp=1, exclude_from_context=True),
        BashExecutionMessage(command="visible", output="y", timestamp=2),
    ]
    result = convert_to_llm(messages)
    assert len(result) == 1
    assert "visible" in _text_of(result[0])


def test_dropped_messages_shift_indices() -> None:
    """Output is not index-aligned with input.

    Stated as its own test because code that zips input and output together
    would silently pair the wrong messages.
    """
    messages = [
        BashExecutionMessage(command="a", output="x", timestamp=1, exclude_from_context=True),
        UserMessage(content="hello", timestamp=2),
    ]
    result = convert_to_llm(messages)
    assert len(result) == 1
    assert result[0].content == "hello"


def test_branch_summary_framing_is_byte_exact() -> None:
    result = convert_to_llm([BranchSummaryMessage(summary="S", from_id="f", timestamp=7)])[0]
    assert _text_of(result) == BRANCH_SUMMARY_PREFIX + "S" + BRANCH_SUMMARY_SUFFIX
    assert result.timestamp == 7


def test_compaction_summary_framing_is_byte_exact() -> None:
    result = convert_to_llm([CompactionSummaryMessage(summary="S", tokens_before=1, timestamp=7)])[
        0
    ]
    assert _text_of(result) == COMPACTION_SUMMARY_PREFIX + "S" + COMPACTION_SUMMARY_SUFFIX


def test_summary_suffix_asymmetry_is_preserved() -> None:
    """The compaction suffix has a leading newline; the branch one does not.

    This looks like a typo in OpenClaw and is not corrected here — the text
    is part of the prompt, and "fixing" it changes model input.
    """
    assert COMPACTION_SUMMARY_SUFFIX == "\n</summary>"
    assert BRANCH_SUMMARY_SUFFIX == "</summary>"
    assert COMPACTION_SUMMARY_PREFIX.endswith("<summary>\n")
    assert BRANCH_SUMMARY_PREFIX.endswith("<summary>\n")


def test_custom_message_with_block_content_is_passed_through() -> None:
    """A content list is used as-is, not re-wrapped."""
    blocks = [TextContent(text="one"), TextContent(text="two")]
    message = CustomMessage(custom_type="t", content=blocks, display=True, timestamp=1)
    result = convert_to_llm([message])[0]
    assert result.content == blocks


def test_provider_visible_messages_pass_through_identically() -> None:
    """Same object, not a copy — the TS returns ``message`` unchanged."""
    user = UserMessage(content="hi", timestamp=1)
    assistant = AssistantMessage(api="anthropic-messages", provider="anthropic", model="m")
    result = convert_to_llm([user, assistant])
    assert result[0] is user
    assert result[1] is assistant


def test_unrecognized_roles_are_dropped_not_raised() -> None:
    """The ``default`` arm.

    A message type from a newer build must not make an older build unable
    to render the conversation at all.
    """

    class FutureMessage:
        role = "somethingNew"

    result = convert_to_llm([FutureMessage()])  # type: ignore[list-item]
    assert result == []


def test_convert_to_llm_on_an_empty_transcript() -> None:
    assert convert_to_llm([]) == []


def test_as_agent_message_is_identity() -> None:
    """A type assertion in the TS; a no-op here, kept for call-site parity."""
    message = UserMessage(content="x", timestamp=1)
    assert as_agent_message(message) is message
