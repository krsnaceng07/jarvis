"""Build model context from an ordered session branch.

Port of ``packages/agent-core/src/harness/session/session.ts`` (85 lines).

This module is small and unusually load-bearing. It is the function that
decides what the model actually sees, so every bug here is invisible in
tests that check the session *tree* and only shows up as the model behaving
as though it forgot something. The two places that happens are marked
inline: the replay window after a compaction, and the "last one wins" state
scan.
"""

from __future__ import annotations

from .harness_types import (
    BranchSummaryEntry,
    CompactionEntry,
    CustomMessageEntry,
    MessageEntry,
    ModelChangeEntry,
    SessionContext,
    SessionModelRef,
    SessionTreeEntry,
    ThinkingLevelChangeEntry,
)
from .messages import (
    as_agent_message,
    create_branch_summary_message,
    create_compaction_summary_message,
    create_custom_message,
)
from .types import AgentMessage

__all__ = ["build_session_context"]


def build_session_context(path_entries: list[SessionTreeEntry]) -> SessionContext:
    """Assemble the model-visible context for one branch of a session.

    Parity: ``buildSessionContext``.

    ``path_entries`` is a root-to-leaf ordered path, not the whole tree.
    Returns the messages to send, the effective thinking level, and the
    effective model.
    """
    thinking_level = "off"
    model: SessionModelRef | None = None
    compaction: CompactionEntry | None = None

    # State scan: later entries overwrite earlier ones, so the *last*
    # matching entry wins. An early `break` on the first match would pin
    # the session to a stale model or thinking level after the user
    # switched mid-conversation.
    for entry in path_entries:
        if isinstance(entry, ThinkingLevelChangeEntry):
            thinking_level = entry.thinking_level
        elif isinstance(entry, ModelChangeEntry):
            model = SessionModelRef(provider=entry.provider, model_id=entry.model_id)
        elif isinstance(entry, MessageEntry):
            message = entry.message
            # An assistant reply records the model that produced it, so it
            # counts as a model marker too — a resumed session with no
            # explicit model_change entry still resolves a model.
            if message is not None and getattr(message, "role", None) == "assistant":
                model = SessionModelRef(provider=message.provider, model_id=message.model)
        elif isinstance(entry, CompactionEntry):
            compaction = entry

    messages: list[AgentMessage] = []

    def append_message(entry: SessionTreeEntry) -> None:
        """Append the model-visible message an entry carries, if any.

        Most entry types contribute nothing: `custom` (as opposed to
        `custom_message`), `label`, `session_info`, `leaf`, `model_change`,
        `thinking_level_change` and `compaction` are all session
        bookkeeping and must stay out of model context.
        """
        if isinstance(entry, MessageEntry):
            if entry.message is not None:
                messages.append(entry.message)
        elif isinstance(entry, CustomMessageEntry):
            messages.append(
                as_agent_message(
                    create_custom_message(
                        entry.custom_type,
                        entry.content,
                        entry.display,
                        entry.details,
                        entry.timestamp,
                    )
                )
            )
        elif isinstance(entry, BranchSummaryEntry) and entry.summary:
            # An empty summary is skipped, not rendered as empty framing —
            # otherwise the model sees a `<summary></summary>` block that
            # says a branch happened but conveys nothing.
            messages.append(
                as_agent_message(
                    create_branch_summary_message(entry.summary, entry.from_id, entry.timestamp)
                )
            )

    if compaction is None:
        for entry in path_entries:
            append_message(entry)
        return SessionContext(messages=messages, thinking_level=thinking_level, model=model)

    messages.append(
        as_agent_message(
            create_compaction_summary_message(
                compaction.summary, compaction.tokens_before, compaction.timestamp
            )
        )
    )

    compaction_idx = _index_of_compaction(path_entries, compaction.id)

    # The synthetic summary replaces only history *before* the retained
    # tail. Entries from `first_kept_entry_id` up to the compaction still
    # replay, and so does everything after it — otherwise post-compaction
    # turns silently disappear from model context and the model answers as
    # though the last few exchanges never happened.
    found_first_kept = False
    for entry in path_entries[:compaction_idx]:
        if entry.id == compaction.first_kept_entry_id:
            found_first_kept = True
        if found_first_kept:
            append_message(entry)

    for entry in path_entries[compaction_idx + 1 :]:
        append_message(entry)

    return SessionContext(messages=messages, thinking_level=thinking_level, model=model)


def _index_of_compaction(path_entries: list[SessionTreeEntry], compaction_id: str) -> int:
    """Position of the compaction entry with ``compaction_id``.

    Parity: the ``findIndex`` in ``buildSessionContext``. Split out because
    TypeScript's ``findIndex`` returns ``-1`` when absent, and ``-1`` fed to
    Python slices would quietly mean "all but the last entry" — a wrong
    answer rather than a loud one. The entry came from ``path_entries``, so
    absence is a caller bug and raising is correct.
    """
    for index, entry in enumerate(path_entries):
        if isinstance(entry, CompactionEntry) and entry.id == compaction_id:
            return index
    raise ValueError(f"compaction entry {compaction_id!r} is not on this path")
