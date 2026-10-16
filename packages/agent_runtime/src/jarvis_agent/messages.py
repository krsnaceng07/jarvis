"""jarvis_agent.messages — harness transcript to LLM message conversion.

OpenClaw parity: ``packages/agent-core/src/harness/messages.ts``.

This is the boundary between the two message worlds. The harness transcript
holds four extra roles that no provider understands — shell executions,
application-defined content, branch summaries, compaction summaries — and
:func:`convert_to_llm` renders each into a plain user message or drops it.

Timestamp handling is the subtle part
=====================================
The session tree persists timestamps as ISO strings while messages use
millisecond ints, so a conversion happens here. There are two functions and
they behave differently *on purpose*:

:func:`require_session_timestamp_ms`
    Raises. Used by the ``create_*_message`` constructors, where a bad
    timestamp means the caller passed garbage and there is still a caller to
    tell. Failing here is cheap.

:func:`parse_session_timestamp_ms`
    Returns ``None``. Used when reading persisted data, where a bad value
    means an already-written row is corrupt and raising would make the whole
    session unloadable.

:func:`normalize_compaction_summary_timestamp` builds on the second and
falls back to ``0`` rather than propagating ``None``. That is deliberate in
the TS and the comment there explains why: session order is already
preserved by entry id, so a corrupt timestamp costs nothing, while aborting
context conversion would cost the user their conversation.

Prompt-cache anchoring
======================
A custom message whose ``details["runtimeContextCarrier"]`` is exactly
``True`` is marked on the resulting user message. Providers must not anchor
a prompt-cache breakpoint on it: its bytes change every turn, so a
breakpoint there destroys the cache hit rate instead of helping. The check
is ``is True``, not truthiness — an arbitrary truthy value in persisted
application metadata must not silently disable caching.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, TypeAlias, Union

from jarvis_llm.types import (
    AssistantMessage,
    ImageContent,
    Message,
    TextContent,
    ToolResultMessage,
    UserMessage,
)

from .types import (
    AgentMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
    CustomMessage,
)

#: Parity: ``HarnessMessage``. The union ``convert_to_llm`` accepts. It is
#: the same set as :data:`~jarvis_agent.types.AgentMessage`; the separate
#: name exists in the TS to keep harness-owned call sites explicit, and is
#: kept for the same reason.
HarnessMessage: TypeAlias = Union[
    AgentMessage,
    BashExecutionMessage,
    CustomMessage,
    BranchSummaryMessage,
    CompactionSummaryMessage,
]


def as_agent_message(message: HarnessMessage) -> AgentMessage:
    """Parity: ``asAgentMessage``.

    A no-op at runtime — in the TS it is a type assertion. Kept so ported
    call sites read identically and so the harness boundary stays visible
    in a grep.
    """
    return message


# ─────────────────────────────────────────────────────────────────────
# Timestamps
# ─────────────────────────────────────────────────────────────────────


def parse_session_timestamp_ms(value: Any) -> int | None:
    """Parse an ISO timestamp string to epoch milliseconds, or ``None``.

    Parity: ``parseSessionTimestampMs``, including ``Date.parse``
    semantics: a non-string, an empty or whitespace-only string, or an
    unparseable value all yield ``None`` rather than raising.

    ``Date.parse`` accepts a trailing ``Z``; :meth:`datetime.fromisoformat`
    on Python 3.10 does not, so it is translated. Milliseconds are truncated
    toward zero, matching ``Date.parse``.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # `Date.parse` treats a bare date-time as local time; the session
        # writer always emits UTC, so assuming UTC here is the closest
        # faithful reading and avoids a value that shifts by host timezone.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def require_session_timestamp_ms(value: str, label: str) -> int:
    """Parse or raise. Parity: ``requireSessionTimestampMs``.

    The message text is kept verbatim (``"<label> must be a valid
    timestamp"``) because ``messages.test.ts`` asserts on it.
    """
    parsed = parse_session_timestamp_ms(value)
    if parsed is None:
        raise ValueError(f"{label} must be a valid timestamp")
    return parsed


def normalize_compaction_summary_timestamp(timestamp: int | str) -> int:
    """Coerce a persisted compaction timestamp to milliseconds.

    Parity: ``normalizeCompactionSummaryTimestamp``.

    Falls back to ``0`` for a corrupt value instead of raising. Quoting the
    reason from the TS: corrupt persisted rows should not abort context
    conversion, and session order is already preserved by entry id. Losing
    one timestamp is survivable; losing the session is not.

    ``bool`` is rejected before the ``int`` check — ``isinstance(True, int)``
    is ``True`` in Python, and a stray boolean should take the parse path and
    become ``0`` rather than silently becoming a timestamp of ``1``.
    """
    if isinstance(timestamp, bool):
        return 0
    if isinstance(timestamp, int):
        return timestamp
    parsed = parse_session_timestamp_ms(timestamp)
    return parsed if parsed is not None else 0


# ─────────────────────────────────────────────────────────────────────
# Summary framing text
# ─────────────────────────────────────────────────────────────────────

#: Parity: ``COMPACTION_SUMMARY_PREFIX``. Byte-exact, including both
#: newlines after the sentence and the newline after ``<summary>`` — the
#: text is part of the prompt, so whitespace changes change model behaviour.
COMPACTION_SUMMARY_PREFIX = (
    "The conversation history before this point was compacted into the "
    "following summary:\n\n<summary>\n"
)

#: Parity: ``COMPACTION_SUMMARY_SUFFIX``. Leading newline included.
COMPACTION_SUMMARY_SUFFIX = "\n</summary>"

#: Parity: ``BRANCH_SUMMARY_PREFIX``.
BRANCH_SUMMARY_PREFIX = (
    "The following is a summary of a branch that this conversation came back from:\n\n<summary>\n"
)

#: Parity: ``BRANCH_SUMMARY_SUFFIX``. Note the asymmetry with the compaction
#: suffix: this one has **no** leading newline. That is in the TS and is
#: preserved rather than tidied.
BRANCH_SUMMARY_SUFFIX = "</summary>"


# ─────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────


def bash_execution_to_text(msg: BashExecutionMessage) -> str:
    """Render a shell execution record as model-visible text.

    Parity: ``bashExecutionToText``.

    Two details worth naming. The cancelled branch and the exit-code branch
    are mutually exclusive (``else if``): a cancelled command reports
    cancellation, never its exit code, because an interrupted process's code
    is misleading. And the exit-code line appears only for a non-zero,
    non-``None`` code — ``0`` is success and needs no comment, which is why
    the check is explicit rather than a truthiness test.
    """
    text = f"Ran `{msg.command}`\n"
    if msg.output:
        text += f"```\n{msg.output}\n```"
    else:
        text += "(no output)"

    if msg.cancelled:
        text += "\n\n(command cancelled)"
    elif msg.exit_code is not None and msg.exit_code != 0:
        text += f"\n\nCommand exited with code {msg.exit_code}"

    if msg.truncated and msg.full_output_path:
        text += f"\n\n[Output truncated. Full output: {msg.full_output_path}]"
    return text


# ─────────────────────────────────────────────────────────────────────
# Constructors
# ─────────────────────────────────────────────────────────────────────


def create_branch_summary_message(
    summary: str, from_id: str, timestamp: str
) -> BranchSummaryMessage:
    """Parity: ``createBranchSummaryMessage``. Raises on a bad timestamp."""
    return BranchSummaryMessage(
        summary=summary,
        from_id=from_id,
        timestamp=require_session_timestamp_ms(timestamp, "branch summary timestamp"),
    )


def create_compaction_summary_message(
    summary: str, tokens_before: int, timestamp: str
) -> CompactionSummaryMessage:
    """Parity: ``createCompactionSummaryMessage``. Raises on a bad timestamp.

    Note the asymmetry with reading: this constructor is strict, while
    :func:`normalize_compaction_summary_timestamp` is lenient. Writing a
    corrupt row is a bug to catch now; reading one is a fact to survive.
    """
    return CompactionSummaryMessage(
        summary=summary,
        tokens_before=tokens_before,
        timestamp=require_session_timestamp_ms(timestamp, "compaction summary timestamp"),
    )


def create_custom_message(
    custom_type: str,
    content: str | list[TextContent | ImageContent],
    display: bool,
    details: Any,
    timestamp: str,
) -> CustomMessage:
    """Parity: ``createCustomMessage``. Raises on a bad timestamp."""
    return CustomMessage(
        custom_type=custom_type,
        content=content,
        display=display,
        details=details,
        timestamp=require_session_timestamp_ms(timestamp, "custom message timestamp"),
    )


# ─────────────────────────────────────────────────────────────────────
# Conversion
# ─────────────────────────────────────────────────────────────────────


def _is_runtime_context_carrier(details: Any) -> bool:
    """Whether ``details.runtimeContextCarrier`` is exactly ``True``.

    Parity: ``?.runtimeContextCarrier === true``. The strict comparison
    matters — ``details`` is application-supplied and persisted, so a
    truthy string or a ``1`` must not silently disable prompt-cache
    anchoring for the whole conversation.

    Reads the camelCase key because ``details`` is opaque application data
    that round-trips through JSON unchanged; it is not a ported field.
    """
    if isinstance(details, dict):
        return details.get("runtimeContextCarrier") is True
    return getattr(details, "runtime_context_carrier", None) is True


def _convert_one(message: HarnessMessage) -> Message | None:
    """Convert a single harness message, or ``None`` to drop it."""
    role = getattr(message, "role", None)

    if role == "bashExecution":
        assert isinstance(message, BashExecutionMessage)
        if message.exclude_from_context:
            # Stays in session history, hidden from model context.
            return None
        return UserMessage(
            content=[TextContent(text=bash_execution_to_text(message))],
            timestamp=message.timestamp,
        )

    if role == "custom":
        assert isinstance(message, CustomMessage)
        content: list[TextContent | ImageContent]
        if isinstance(message.content, str):
            content = [TextContent(text=message.content)]
        else:
            content = message.content
        carrier = _is_runtime_context_carrier(message.details)
        return UserMessage(
            content=content,
            timestamp=message.timestamp,
            # The TS spreads the field in only when true, so an ordinary
            # message has it *absent* rather than false. `None` is this
            # port's absent, and `to_dict` omits it.
            runtime_context_carrier=True if carrier else None,
        )

    if role == "branchSummary":
        assert isinstance(message, BranchSummaryMessage)
        return UserMessage(
            content=[
                TextContent(text=BRANCH_SUMMARY_PREFIX + message.summary + BRANCH_SUMMARY_SUFFIX)
            ],
            timestamp=message.timestamp,
        )

    if role == "compactionSummary":
        assert isinstance(message, CompactionSummaryMessage)
        return UserMessage(
            content=[
                TextContent(
                    text=COMPACTION_SUMMARY_PREFIX + message.summary + COMPACTION_SUMMARY_SUFFIX
                )
            ],
            timestamp=normalize_compaction_summary_timestamp(message.timestamp),
        )

    if role in ("user", "assistant", "toolResult"):
        # Already provider-visible; passed through unchanged, same object.
        assert isinstance(message, (UserMessage, AssistantMessage, ToolResultMessage))
        return message

    # Parity: the `default` arm. An unrecognized role is dropped rather than
    # raising — a newer build's message type must not make an older build
    # unable to render the conversation at all.
    return None


def convert_to_llm(messages: list[AgentMessage]) -> list[Message]:
    """Convert a harness transcript to the provider-facing sequence.

    Parity: ``convertToLlm``. Dropped messages are filtered out, so the
    returned list is generally shorter than the input and indices do not
    correspond.

    This function must not raise: it is wired in as the
    ``convert_to_llm`` hook, whose contract is to return a safe fallback
    instead. Every branch above either produces a message or drops it.
    """
    converted: list[Message] = []
    for message in messages:
        result = _convert_one(message)
        if result is not None:
            converted.append(result)
    return converted


__all__ = [
    "BRANCH_SUMMARY_PREFIX",
    "BRANCH_SUMMARY_SUFFIX",
    "COMPACTION_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_SUFFIX",
    "BashExecutionMessage",
    "BranchSummaryMessage",
    "CompactionSummaryMessage",
    "CustomMessage",
    "HarnessMessage",
    "as_agent_message",
    "bash_execution_to_text",
    "convert_to_llm",
    "create_branch_summary_message",
    "create_compaction_summary_message",
    "create_custom_message",
    "normalize_compaction_summary_timestamp",
    "parse_session_timestamp_ms",
    "require_session_timestamp_ms",
]
