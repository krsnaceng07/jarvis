"""Branch summarization: summarize an abandoned branch when navigating away.

Port of ``packages/agent-core/src/harness/compaction/branch-summarization.ts``.
"""

from __future__ import annotations

import inspect
import time
from dataclasses import dataclass, field
from typing import Any

from jarvis_llm import Context, Model, SimpleStreamOptions, TextContent, UserMessage

from .compaction import SUMMARIZATION_SYSTEM_PROMPT, estimate_tokens
from .compaction_utils import (
    compute_file_lists,
    create_file_ops,
    extract_file_ops_from_message,
    format_file_operations,
    serialize_conversation,
)
from .harness_types import (
    BranchSummaryError,
    BranchSummaryResult,
    FileOperations,
    Result,
    SessionTreeEntry,
    err,
    ok,
)
from .messages import (
    as_agent_message,
    convert_to_llm,
    create_branch_summary_message,
    create_compaction_summary_message,
    create_custom_message,
)
from .runtime_deps import AgentCoreCompletionRuntimeDeps, resolve_agent_core_complete_fn
from .types import AgentMessage, StreamFn


@dataclass(frozen=True)
class BranchSummaryDetails:
    """File-operation details stored on generated branch summary entries.

    Parity: ``BranchSummaryDetails``.
    """

    read_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BranchPreparation:
    """Prepared branch content for summarization. Parity: ``BranchPreparation``."""

    messages: list[AgentMessage] = field(default_factory=list)
    file_ops: FileOperations = field(default_factory=create_file_ops)
    total_tokens: int = 0


@dataclass(frozen=True)
class BranchPathEntry:
    """Minimal tree entry shape needed to compare two session branches.

    Parity: ``BranchPathEntry``. Structural in TS; callers may pass any
    object with ``id`` and ``parent_id`` — only ``id`` is consulted here.
    """

    id: str = ""
    parent_id: str | None = None


@dataclass(frozen=True)
class CollectBranchPathEntriesResult:
    """Branch entries selected after comparing old and target paths.

    Parity: ``CollectBranchPathEntriesResult<TEntry>``.
    """

    entries: list = field(default_factory=list)
    common_ancestor_id: str | None = None


@dataclass(frozen=True)
class GenerateBranchSummaryOptions:
    """Options for generating a branch summary.

    Parity: the (non-exported) ``GenerateBranchSummaryOptions``.
    """

    model: Model = None  # type: ignore[assignment]
    api_key: str = ""
    headers: dict[str, str] | None = None
    signal: Any = None
    runtime: AgentCoreCompletionRuntimeDeps | None = None
    stream_fn: StreamFn | None = None
    custom_instructions: str | None = None
    replace_instructions: bool | None = None
    reserve_tokens: int = 16384


def collect_entries_for_branch_summary_from_branches(
    old_branch: list, target_branch: list
) -> CollectBranchPathEntriesResult:
    """Collect entries to summarize before navigating to a different entry.

    Parity: ``collectEntriesForBranchSummaryFromBranches``. Entries after
    the deepest common ancestor on the old branch are the abandoned work.
    """
    old_path = {entry.id for entry in old_branch}
    common_ancestor_id: str | None = None
    for target_entry in reversed(target_branch):
        if target_entry.id in old_path:
            common_ancestor_id = target_entry.id
            break

    if common_ancestor_id is None:
        first_summarized_index = 0
    else:
        first_summarized_index = (
            next(
                (i for i, entry in enumerate(old_branch) if entry.id == common_ancestor_id),
                -1,
            )
            + 1
        )
    return CollectBranchPathEntriesResult(
        entries=list(old_branch[first_summarized_index:]),
        common_ancestor_id=common_ancestor_id,
    )


def _get_message_from_entry(entry: SessionTreeEntry) -> AgentMessage | None:
    """Parity: the local ``getMessageFromEntry``.

    Differs from compaction's: tool results are dropped (their content is
    noise for a branch summary), while compaction entries *do* project —
    an old summary is exactly the compressed context a branch recap needs.
    """
    entry_type = getattr(entry, "type", None)
    if entry_type == "message":
        if getattr(entry.message, "role", None) == "toolResult":
            return None
        return entry.message
    if entry_type == "custom_message":
        return as_agent_message(
            create_custom_message(
                entry.custom_type,
                entry.content,
                entry.display,
                entry.details,
                entry.timestamp,
            )
        )
    if entry_type == "branch_summary":
        return as_agent_message(
            create_branch_summary_message(entry.summary, entry.from_id, entry.timestamp)
        )
    if entry_type == "compaction":
        return as_agent_message(
            create_compaction_summary_message(entry.summary, entry.tokens_before, entry.timestamp)
        )
    return None


def _details_get(details: Any, name: str) -> Any:
    if isinstance(details, dict):
        return details.get(name)
    return getattr(details, name, None)


def prepare_branch_entries(
    entries: list[SessionTreeEntry], token_budget: int = 0
) -> BranchPreparation:
    """Prepare branch entries for summarization within a token budget.

    Parity: ``prepareBranchEntries``.
    """
    messages: list[AgentMessage] = []
    file_ops = create_file_ops()
    total_tokens = 0
    for entry in entries:
        if (
            getattr(entry, "type", None) == "branch_summary"
            and not getattr(entry, "from_hook", None)
            and getattr(entry, "details", None)
        ):
            details = entry.details
            read_files = _details_get(details, "read_files")
            if isinstance(read_files, list):
                for f in read_files:
                    file_ops.read.add(f)
            modified_files = _details_get(details, "modified_files")
            if isinstance(modified_files, list):
                for f in modified_files:
                    file_ops.edited.add(f)
    for entry in reversed(entries):
        message = _get_message_from_entry(entry)
        if message is None:
            continue
        extract_file_ops_from_message(message, file_ops)

        tokens = estimate_tokens(message)
        if token_budget > 0 and total_tokens + tokens > token_budget:
            # Prefer already-compressed summaries when the budget is almost
            # filled; they preserve older branch context better than dropping
            # the whole prefix.
            if getattr(entry, "type", None) in ("compaction", "branch_summary"):
                if total_tokens < token_budget * 0.9:
                    messages.insert(0, message)
                    total_tokens += tokens
            break

        messages.insert(0, message)
        total_tokens += tokens

    return BranchPreparation(messages=messages, file_ops=file_ops, total_tokens=total_tokens)


BRANCH_SUMMARY_PREAMBLE = """The user explored a different conversation branch before returning here.
Summary of that exploration:

"""

_BRANCH_SUMMARY_PROMPT = """Create a structured summary of this conversation branch for context when returning later.

Use this EXACT format:

## Goal
[What was the user trying to accomplish in this branch?]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Work that was started but not finished]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [What should happen next to continue this work]

Keep each section concise. Preserve exact file paths, function names, and error messages."""


async def generate_branch_summary(
    entries: list[SessionTreeEntry], options: GenerateBranchSummaryOptions
) -> Result:
    """Generate a summary for abandoned branch entries.

    Parity: ``generateBranchSummary``.
    """
    model = options.model
    api_key = options.api_key
    headers = options.headers
    signal = options.signal
    custom_instructions = options.custom_instructions
    replace_instructions = options.replace_instructions
    reserve_tokens = options.reserve_tokens
    context_window = model.context_window or 128000
    token_budget = context_window - reserve_tokens

    preparation = prepare_branch_entries(entries, token_budget)
    messages = preparation.messages
    file_ops = preparation.file_ops

    if not messages:
        return ok(
            BranchSummaryResult(summary="No content to summarize", read_files=[], modified_files=[])
        )
    llm_messages = convert_to_llm(messages)
    conversation_text = serialize_conversation(llm_messages)
    if replace_instructions and custom_instructions:
        instructions = custom_instructions
    elif custom_instructions:
        instructions = f"{_BRANCH_SUMMARY_PROMPT}\n\nAdditional focus: {custom_instructions}"
    else:
        instructions = _BRANCH_SUMMARY_PROMPT
    prompt_text = f"<conversation>\n{conversation_text}\n</conversation>\n\n{instructions}"

    summarization_messages = [
        UserMessage(
            content=[TextContent(text=prompt_text)],
            timestamp=int(time.time() * 1000),
        )
    ]
    context = Context(system_prompt=SUMMARIZATION_SYSTEM_PROMPT, messages=summarization_messages)
    stream_options = SimpleStreamOptions(
        api_key=api_key, headers=headers, signal=signal, max_tokens=2048
    )
    if options.stream_fn is not None:
        response = options.stream_fn(model, context, stream_options)
        if inspect.isawaitable(response):
            response = await response
        response = await response.result()
    else:
        response = resolve_agent_core_complete_fn(options.runtime)(model, context, stream_options)
        if inspect.isawaitable(response):
            response = await response
    if response.stop_reason == "aborted":
        return err(
            BranchSummaryError("aborted", response.error_message or "Branch summary aborted")
        )
    if response.stop_reason == "error":
        return err(
            BranchSummaryError(
                "summarization_failed",
                f"Branch summary failed: {response.error_message or 'Unknown error'}",
            )
        )

    summary = "\n".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    )
    summary = BRANCH_SUMMARY_PREAMBLE + summary
    read_files, modified_files = compute_file_lists(file_ops)
    summary += format_file_operations(read_files, modified_files)

    return ok(
        BranchSummaryResult(
            summary=summary or "No summary generated",
            read_files=read_files,
            modified_files=modified_files,
        )
    )


__all__ = [
    "BRANCH_SUMMARY_PREAMBLE",
    "BranchPathEntry",
    "BranchPreparation",
    "BranchSummaryDetails",
    "CollectBranchPathEntriesResult",
    "GenerateBranchSummaryOptions",
    "collect_entries_for_branch_summary_from_branches",
    "generate_branch_summary",
    "prepare_branch_entries",
]
