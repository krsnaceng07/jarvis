"""Context compaction: token estimation, cut-point selection, summarization.

Port of ``packages/agent-core/src/harness/compaction/compaction.ts`` and
``src/agents/compaction.ts`` (multi-stage summarisation extension).

Signatures follow the TS positional parameter order so call sites read the
same against either codebase. Results are :class:`Ok`/:class:`Err` values,
never raised ``CompactionError``s — compaction failure is an expected
outcome the caller handles by keeping the uncompacted transcript.
"""

from __future__ import annotations

import inspect
import math
import time
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

from jarvis_llm import (
    AssistantMessage,
    Context,
    Model,
    SimpleStreamOptions,
    TextContent,
    Usage,
    UserMessage,
    resolve_claude_fable5_model_identity,
)

from .compaction_utils import (
    compute_file_lists,
    create_file_ops,
    extract_file_ops_from_message,
    get_compaction_content_block_text,
    safe_json_stringify,
    serialize_conversation,
)
from .harness_types import (
    CompactionError,
    Err,
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
from .reasoning import resolve_agent_reasoning_option
from .runtime_deps import AgentCoreCompletionRuntimeDeps, resolve_agent_core_complete_fn
from .session_context import build_session_context
from .types import AgentMessage, StreamFn, ThinkingLevel


@dataclass(frozen=True)
class CompactionDetails:
    """File-operation details stored on generated compaction entries.

    Parity: ``CompactionDetails``.
    """

    read_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)


def _details_get(details: Any, name: str) -> Any:
    """Read a details field that may come from a dataclass or persisted dict."""
    if isinstance(details, dict):
        return details.get(name)
    return getattr(details, name, None)


def _extract_file_operations(
    messages: list[AgentMessage],
    entries: list[SessionTreeEntry],
    prev_compaction_index: int,
) -> FileOperations:
    """Parity: the local ``extractFileOperations``."""
    file_ops = create_file_ops()
    if prev_compaction_index >= 0:
        prev_compaction = entries[prev_compaction_index]
        if not getattr(prev_compaction, "from_hook", None) and getattr(
            prev_compaction, "details", None
        ):
            details = prev_compaction.details
            read_files = _details_get(details, "read_files")
            if isinstance(read_files, list):
                for f in read_files:
                    file_ops.read.add(f)
            modified_files = _details_get(details, "modified_files")
            if isinstance(modified_files, list):
                for f in modified_files:
                    file_ops.edited.add(f)
    for msg in messages:
        extract_file_ops_from_message(msg, file_ops)

    return file_ops


def _get_message_from_entry(entry: SessionTreeEntry) -> AgentMessage | None:
    """Parity: the local ``getMessageFromEntry``."""
    entry_type = getattr(entry, "type", None)
    if entry_type == "message":
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


def _get_message_from_entry_for_compaction(
    entry: SessionTreeEntry,
) -> AgentMessage | None:
    """Parity: ``getMessageFromEntryForCompaction``.

    Compaction entries yield no message here: an old summary must not be
    re-summarized as transcript content — it feeds in separately as
    ``previous_summary``.
    """
    if getattr(entry, "type", None) == "compaction":
        return None
    return _get_message_from_entry(entry)


@dataclass(frozen=True)
class CompactionResult:
    """Generated compaction data ready to persist. Parity: ``CompactionResult<T>``."""

    summary: str = ""
    first_kept_entry_id: str = ""
    tokens_before: int = 0
    details: Any = None


@dataclass(frozen=True)
class CompactionSettings:
    """Compaction thresholds and retention settings. Parity: ``CompactionSettings``."""

    enabled: bool = True
    reserve_tokens: int = 16384
    keep_recent_tokens: int = 20000


#: Default compaction settings used by the harness.
#: Parity: ``DEFAULT_COMPACTION_SETTINGS``.
DEFAULT_COMPACTION_SETTINGS = CompactionSettings(
    enabled=True, reserve_tokens=16384, keep_recent_tokens=20000
)


def calculate_context_tokens(usage: Usage) -> int:
    """Calculate total context tokens from provider usage.

    Parity: ``calculateContextTokens``. The final-iteration context snapshot
    wins over aggregate billing usage; the numeric fallback survives for
    providers that never report a snapshot.
    """
    context_usage = usage.context_usage
    if context_usage is not None and getattr(context_usage, "state", None) == "available":
        return context_usage.total_tokens
    return usage.total_tokens or (usage.input + usage.output + usage.cache_read + usage.cache_write)


def _get_assistant_usage(msg: AgentMessage) -> Usage | None:
    """Parity: the local ``getAssistantUsage``."""
    if getattr(msg, "role", None) == "assistant" and hasattr(msg, "usage"):
        if (
            msg.stop_reason != "aborted"
            and msg.stop_reason != "error"
            and msg.usage
            and calculate_context_tokens(msg.usage) > 0
        ):
            return msg.usage
    return None


def get_last_assistant_usage(entries: list[SessionTreeEntry]) -> Usage | None:
    """Return usage from the last valid assistant message in session entries.

    Parity: ``getLastAssistantUsage``.
    """
    for entry in reversed(entries):
        if getattr(entry, "type", None) == "message":
            usage = _get_assistant_usage(entry.message)
            if usage:
                return usage
    return None


@dataclass(frozen=True)
class ContextUsageEstimate:
    """Estimated context-token usage for a message list.

    Parity: ``ContextUsageEstimate``.
    """

    tokens: int = 0
    usage_tokens: int = 0
    trailing_tokens: int = 0
    last_usage_index: int | None = None


def _get_last_assistant_usage_info(
    messages: list[AgentMessage],
) -> tuple[Usage, int] | None:
    """Parity: ``getLastAssistantUsageInfo``.

    Also skips explicitly-unavailable snapshots: a usage block whose context
    state is "unavailable" carries aggregate billing numbers that would wildly
    overestimate the live context.
    """
    for i in range(len(messages) - 1, -1, -1):
        message = messages[i]
        usage = _get_assistant_usage(message)
        if usage and getattr(usage.context_usage, "state", None) != "unavailable":
            return usage, i
    return None


def estimate_context_tokens(messages: list[AgentMessage]) -> ContextUsageEstimate:
    """Estimate context tokens using provider usage when available.

    Parity: ``estimateContextTokens``.
    """
    usage_info = _get_last_assistant_usage_info(messages)

    if usage_info is None:
        estimated = 0
        for message in messages:
            estimated += estimate_tokens(message)
        return ContextUsageEstimate(
            tokens=estimated,
            usage_tokens=0,
            trailing_tokens=estimated,
            last_usage_index=None,
        )

    usage, index = usage_info
    usage_tokens = calculate_context_tokens(usage)
    trailing_tokens = 0
    for message in messages[index + 1 :]:
        trailing_tokens += estimate_tokens(message)

    return ContextUsageEstimate(
        tokens=usage_tokens + trailing_tokens,
        usage_tokens=usage_tokens,
        trailing_tokens=trailing_tokens,
        last_usage_index=index,
    )


def should_compact(context_tokens: int, context_window: int, settings: CompactionSettings) -> bool:
    """Return whether context usage exceeds the compaction threshold.

    Parity: ``shouldCompact``.
    """
    if not settings.enabled:
        return False
    return context_tokens > context_window - settings.reserve_tokens


IMAGE_BLOCK_CHARS = 4800


def _block_get(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _count_content_block_chars(content: list[Any]) -> int:
    """Parity: ``countContentBlockChars``."""
    chars = 0
    for block in content:
        if _block_get(block, "type") == "image":
            chars += IMAGE_BLOCK_CHARS
        else:
            chars += len(get_compaction_content_block_text(block))
    return chars


def estimate_tokens(message: AgentMessage) -> int:
    """Estimate token count for one message via a character heuristic.

    Parity: ``estimateTokens`` — ceil(chars / 4) by role, with images
    charged a flat :data:`IMAGE_BLOCK_CHARS` regardless of payload size.
    """
    chars = 0
    role = getattr(message, "role", None)

    if role == "user":
        content = message.content
        if isinstance(content, str):
            chars = len(content)
        elif isinstance(content, list):
            chars = _count_content_block_chars(content)
        return math.ceil(chars / 4)
    if role == "assistant":
        for block in message.content:
            block_type = _block_get(block, "type")
            if block_type == "text":
                chars += len(_block_get(block, "text") or "")
            elif block_type == "thinking":
                chars += len(_block_get(block, "thinking") or "")
            elif block_type == "toolCall":
                chars += len(_block_get(block, "name") or "") + len(
                    safe_json_stringify(_block_get(block, "arguments"))
                )
        return math.ceil(chars / 4)
    if role in ("custom", "toolResult"):
        content = message.content
        if isinstance(content, str):
            chars = len(content)
        else:
            chars = _count_content_block_chars(content)
        return math.ceil(chars / 4)
    if role == "bashExecution":
        chars = len(message.command) + len(message.output)
        return math.ceil(chars / 4)
    if role in ("branchSummary", "compactionSummary"):
        chars = len(message.summary)
        return math.ceil(chars / 4)

    return 0


def _is_cut_point_message(message: AgentMessage) -> bool:
    """Parity: ``isCutPointMessage`` — everything but a tool result."""
    role = getattr(message, "role", None)
    if role in (
        "user",
        "assistant",
        "bashExecution",
        "custom",
        "branchSummary",
        "compactionSummary",
    ):
        return True
    return False


def _is_turn_start_message(message: AgentMessage) -> bool:
    """Parity: ``isTurnStartMessage``."""
    role = getattr(message, "role", None)
    if role in ("user", "bashExecution", "custom", "branchSummary", "compactionSummary"):
        return True
    return False


def _is_turn_start_entry(entry: SessionTreeEntry) -> bool:
    """Parity: ``isTurnStartEntry``."""
    message = _get_message_from_entry_for_compaction(entry)
    return _is_turn_start_message(message) if message else False


def _find_valid_cut_points(
    entries: list[SessionTreeEntry], start_index: int, end_index: int
) -> list[int]:
    """Parity: ``findValidCutPoints``."""
    cut_points: list[int] = []
    for i in range(start_index, end_index):
        entry = entries[i] if 0 <= i < len(entries) else None
        if entry is None:
            continue
        message = _get_message_from_entry_for_compaction(entry)
        if message and _is_cut_point_message(message):
            cut_points.append(i)
    return cut_points


def find_turn_start_index(
    entries: list[SessionTreeEntry], entry_index: int, start_index: int
) -> int:
    """Find the user-visible message that starts the turn containing an entry.

    Parity: ``findTurnStartIndex``. Returns -1 when no turn start exists in
    range.
    """
    for i in range(entry_index, start_index - 1, -1):
        entry = entries[i] if 0 <= i < len(entries) else None
        if entry is None:
            continue
        if _is_turn_start_entry(entry):
            return i
    return -1


@dataclass(frozen=True)
class CutPointResult:
    """Cut point selected for compaction. Parity: ``CutPointResult``."""

    first_kept_entry_index: int = 0
    turn_start_index: int = -1
    is_split_turn: bool = False


def find_cut_point(
    entries: list[SessionTreeEntry],
    start_index: int,
    end_index: int,
    keep_recent_tokens: int,
) -> CutPointResult:
    """Find the cut point keeping roughly the requested recent-token budget.

    Parity: ``findCutPoint``.
    """
    cut_points = _find_valid_cut_points(entries, start_index, end_index)

    if not cut_points:
        return CutPointResult(
            first_kept_entry_index=start_index, turn_start_index=-1, is_split_turn=False
        )
    accumulated_tokens = 0
    cut_index = cut_points[0]

    for i in range(end_index - 1, start_index - 1, -1):
        entry = entries[i] if 0 <= i < len(entries) else None
        if entry is None:
            continue
        message = _get_message_from_entry_for_compaction(entry)
        if message is None:
            continue
        message_tokens = estimate_tokens(message)
        accumulated_tokens += message_tokens
        if accumulated_tokens >= keep_recent_tokens:
            cut_index = cut_points[-1]
            for cut_point in cut_points:
                if cut_point >= i:
                    cut_index = cut_point
                    break
            break
    # Walk backwards past entries that project nothing into context, so the
    # cut never strands an invisible prefix — but never rewind across a
    # compaction entry, whose summary must stay behind the cut.
    while cut_index > start_index:
        prev_entry = entries[cut_index - 1]
        if prev_entry is None:
            break
        if getattr(prev_entry, "type", None) == "compaction":
            break
        if _get_message_from_entry_for_compaction(prev_entry):
            break
        cut_index -= 1
    cut_entry = entries[cut_index]
    if cut_entry is None:
        raise RuntimeError("compaction cut point does not reference a session entry")
    starts_turn = _is_turn_start_entry(cut_entry)
    turn_start_index = -1 if starts_turn else find_turn_start_index(entries, cut_index, start_index)

    return CutPointResult(
        first_kept_entry_index=cut_index,
        turn_start_index=turn_start_index,
        is_split_turn=not starts_turn and turn_start_index != -1,
    )


SUMMARIZATION_SYSTEM_PROMPT = """You are a context summarization assistant. Your task is to read a conversation between a user and an AI assistant, then produce a structured summary following the exact format specified.

Do NOT continue the conversation. Do NOT respond to any questions in the conversation. ONLY output the structured summary."""

_SUMMARIZATION_PROMPT = """The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Keep each section concise. Preserve exact file paths, function names, and error messages."""

_UPDATE_SUMMARIZATION_PROMPT = """The messages above are NEW conversation messages to incorporate into the existing summary provided in <previous-summary> tags.

Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done" when completed
- UPDATE "Next Steps" based on what was accomplished
- PRESERVE exact file paths, function names, and error messages
- If something is no longer relevant, you may remove it

Use this EXACT format:

## Goal
[Preserve existing goals, add new ones if the task expanded]

## Constraints & Preferences
- [Preserve existing, add new ones discovered]

## Progress
### Done
- [x] [Include previously done items AND newly completed items]

### In Progress
- [ ] [Current work - update based on progress]

### Blocked
- [Current blockers - remove if resolved]

## Key Decisions
- **[Decision]**: [Brief rationale] (preserve all previous, add new)

## Next Steps
1. [Update based on current state]

## Critical Context
- [Preserve important context, add new if needed]

Keep each section concise. Preserve exact file paths, function names, and error messages."""


def _create_summarization_options(
    model: Model,
    max_tokens: int | None,
    api_key: str | None,
    headers: dict[str, str] | None,
    signal: Any | None,
    thinking_level: Optional[ThinkingLevel],
) -> SimpleStreamOptions:
    """Parity: ``createSummarizationOptions``."""
    reasoning = None
    fable_reasoning = (
        model.api in ("anthropic-messages", "bedrock-converse-stream")
        and resolve_claude_fable5_model_identity(model) is not None
    )
    if (model.reasoning or fable_reasoning) and thinking_level:
        reasoning = resolve_agent_reasoning_option(model, thinking_level)
    return SimpleStreamOptions(
        max_tokens=max_tokens,
        signal=signal,
        api_key=api_key,
        headers=headers,
        reasoning=reasoning,
    )


async def _complete_summarization(
    model: Model,
    context: Context,
    options: SimpleStreamOptions,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> AssistantMessage:
    """Parity: ``completeSummarization``."""
    if stream_fn is not None:
        response = stream_fn(model, context, options)
        if inspect.isawaitable(response):
            response = await response
        return await response.result()
    result = resolve_agent_core_complete_fn(runtime)(model, context, options)
    if inspect.isawaitable(result):
        result = await result
    return result


async def _run_summarization_completion(
    *,
    prompt_text: str,
    model: Model,
    max_tokens: int | None,
    api_key: str | None,
    headers: dict[str, str] | None = None,
    signal: Any | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
    error_label: str,
) -> Result:
    """Runs one summarization completion, mapping abort/error stops.

    Parity: ``runSummarizationCompletion``.
    """
    summarization_messages = [
        UserMessage(
            content=[TextContent(text=prompt_text)],
            timestamp=int(time.time() * 1000),
        )
    ]

    response = await _complete_summarization(
        model,
        Context(system_prompt=SUMMARIZATION_SYSTEM_PROMPT, messages=summarization_messages),
        _create_summarization_options(model, max_tokens, api_key, headers, signal, thinking_level),
        stream_fn,
        runtime,
    )
    if response.stop_reason == "aborted":
        return err(CompactionError("aborted", response.error_message or f"{error_label} aborted"))
    if response.stop_reason == "error":
        return err(
            CompactionError(
                "summarization_failed",
                f"{error_label} failed: {response.error_message or 'Unknown error'}",
            )
        )

    return ok(
        "\n".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
    )


async def generate_summary(
    current_messages: list[AgentMessage],
    model: Model,
    reserve_tokens: int,
    api_key: str | None,
    headers: dict[str, str] | None = None,
    signal: Any | None = None,
    custom_instructions: str | None = None,
    previous_summary: str | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> Result:
    """Generate or update a conversation summary for compaction.

    Parity: ``generateSummary``. ``max_tokens`` caps at 80% of the reserve
    so the summary can never itself blow the reserved budget; a model with
    no declared ``max_tokens`` imposes no second cap (``None`` here, TS
    ``+Infinity``).
    """
    computed = math.floor(0.8 * reserve_tokens)
    max_tokens = min(computed, model.max_tokens) if model.max_tokens > 0 else computed
    base_prompt = _UPDATE_SUMMARIZATION_PROMPT if previous_summary else _SUMMARIZATION_PROMPT
    if custom_instructions:
        base_prompt = f"{base_prompt}\n\nAdditional focus: {custom_instructions}"
    llm_messages = convert_to_llm(current_messages)
    conversation_text = serialize_conversation(llm_messages)
    prompt_text = f"<conversation>\n{conversation_text}\n</conversation>\n\n"
    if previous_summary:
        prompt_text += f"<previous-summary>\n{previous_summary}\n</previous-summary>\n\n"
    prompt_text += base_prompt

    return await _run_summarization_completion(
        prompt_text=prompt_text,
        model=model,
        max_tokens=max_tokens,
        api_key=api_key,
        headers=headers,
        signal=signal,
        thinking_level=thinking_level,
        stream_fn=stream_fn,
        runtime=runtime,
        error_label="Summarization",
    )


@dataclass(frozen=True)
class CompactionPreparation:
    """Prepared inputs for a compaction run. Parity: ``CompactionPreparation``."""

    first_kept_entry_id: str = ""
    messages_to_summarize: list[AgentMessage] = field(default_factory=list)
    turn_prefix_messages: list[AgentMessage] = field(default_factory=list)
    is_split_turn: bool = False
    tokens_before: int = 0
    previous_summary: str | None = None
    file_ops: FileOperations = field(default_factory=create_file_ops)
    settings: CompactionSettings = field(default_factory=lambda: DEFAULT_COMPACTION_SETTINGS)


def prepare_compaction(
    path_entries: list[SessionTreeEntry], settings: CompactionSettings
) -> Result:
    """Prepare session entries for compaction.

    Parity: ``prepareCompaction``. ``Ok(None)`` means compaction is not
    applicable right now (already compacted, or nothing to summarize) —
    distinct from ``Err``, which reports a session too broken to compact.
    """
    if not path_entries or getattr(path_entries[-1], "type", None) == "compaction":
        return ok(None)

    prev_compaction_index = -1
    for i in range(len(path_entries) - 1, -1, -1):
        if getattr(path_entries[i], "type", None) == "compaction":
            prev_compaction_index = i
            break

    previous_summary: str | None = None
    boundary_start = 0
    if prev_compaction_index >= 0:
        prev_compaction = path_entries[prev_compaction_index]
        previous_summary = prev_compaction.summary
        first_kept_entry_index = next(
            (
                i
                for i, entry in enumerate(path_entries)
                if entry.id == prev_compaction.first_kept_entry_id
            ),
            -1,
        )
        boundary_start = (
            first_kept_entry_index if first_kept_entry_index >= 0 else prev_compaction_index + 1
        )
    boundary_end = len(path_entries)

    tokens_before = estimate_context_tokens(build_session_context(path_entries).messages).tokens

    cut_point = find_cut_point(
        path_entries, boundary_start, boundary_end, settings.keep_recent_tokens
    )
    first_kept_entry = (
        path_entries[cut_point.first_kept_entry_index]
        if 0 <= cut_point.first_kept_entry_index < len(path_entries)
        else None
    )
    if first_kept_entry is None or not first_kept_entry.id:
        return err(
            CompactionError(
                "invalid_session",
                "First kept entry has no UUID - session may need migration",
            )
        )
    first_kept_entry_id = first_kept_entry.id

    history_end = (
        cut_point.turn_start_index if cut_point.is_split_turn else cut_point.first_kept_entry_index
    )
    messages_to_summarize: list[AgentMessage] = []
    for i in range(boundary_start, history_end):
        entry = path_entries[i] if 0 <= i < len(path_entries) else None
        msg = _get_message_from_entry_for_compaction(entry) if entry else None
        if msg:
            messages_to_summarize.append(msg)
    turn_prefix_messages: list[AgentMessage] = []
    if cut_point.is_split_turn:
        for i in range(cut_point.turn_start_index, cut_point.first_kept_entry_index):
            entry = path_entries[i] if 0 <= i < len(path_entries) else None
            msg = _get_message_from_entry_for_compaction(entry) if entry else None
            if msg:
                turn_prefix_messages.append(msg)
    if not messages_to_summarize and not turn_prefix_messages:
        return ok(None)
    file_ops = _extract_file_operations(messages_to_summarize, path_entries, prev_compaction_index)
    if cut_point.is_split_turn:
        for msg in turn_prefix_messages:
            extract_file_ops_from_message(msg, file_ops)

    return ok(
        CompactionPreparation(
            first_kept_entry_id=first_kept_entry_id,
            messages_to_summarize=messages_to_summarize,
            turn_prefix_messages=turn_prefix_messages,
            is_split_turn=cut_point.is_split_turn,
            tokens_before=tokens_before,
            previous_summary=previous_summary,
            file_ops=file_ops,
            settings=settings,
        )
    )


_TURN_PREFIX_SUMMARIZATION_PROMPT = """This is the PREFIX of a turn that was too large to keep. The SUFFIX (recent work) is retained.

Summarize the prefix to provide context for the retained suffix:

## Original Request
[What did the user ask for in this turn?]

## Early Progress
- [Key decisions and work done in the prefix]

## Context for Suffix
- [Information needed to understand the retained recent work]

Be concise. Focus on what's needed to understand the kept suffix."""


async def compact(
    preparation: CompactionPreparation,
    model: Model,
    api_key: str | None,
    headers: dict[str, str] | None = None,
    custom_instructions: str | None = None,
    signal: Any | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> Result:
    """Generate compaction summary data from prepared session history.

    Parity: ``compact``. On a split turn the history and turn-prefix
    summaries run sequentially, never concurrently.
    """
    first_kept_entry_id = preparation.first_kept_entry_id
    messages_to_summarize = preparation.messages_to_summarize
    turn_prefix_messages = preparation.turn_prefix_messages
    is_split_turn = preparation.is_split_turn
    tokens_before = preparation.tokens_before
    previous_summary = preparation.previous_summary
    file_ops = preparation.file_ops
    settings = preparation.settings

    if not first_kept_entry_id:
        return err(
            CompactionError(
                "invalid_session",
                "First kept entry has no UUID - session may need migration",
            )
        )

    if is_split_turn and turn_prefix_messages:
        history_result = (
            await generate_summary(
                messages_to_summarize,
                model,
                settings.reserve_tokens,
                api_key,
                headers,
                signal,
                custom_instructions,
                previous_summary,
                thinking_level,
                stream_fn,
                runtime,
            )
            if messages_to_summarize
            else ok("No prior history.")
        )
        if isinstance(history_result, Err):
            return err(history_result.error)
        turn_prefix_result = await _generate_turn_prefix_summary(
            turn_prefix_messages,
            model,
            settings.reserve_tokens,
            api_key,
            headers,
            signal,
            thinking_level,
            stream_fn,
            runtime,
        )
        if isinstance(turn_prefix_result, Err):
            return err(turn_prefix_result.error)
        summary = (
            f"{history_result.value}\n\n---\n\n"
            f"**Turn Context (split turn):**\n\n{turn_prefix_result.value}"
        )
    else:
        summary_result = await generate_summary(
            messages_to_summarize,
            model,
            settings.reserve_tokens,
            api_key,
            headers,
            signal,
            custom_instructions,
            previous_summary,
            thinking_level,
            stream_fn,
            runtime,
        )
        if isinstance(summary_result, Err):
            return err(summary_result.error)
        summary = summary_result.value

    from .compaction_utils import format_file_operations

    read_files, modified_files = compute_file_lists(file_ops)
    summary += format_file_operations(read_files, modified_files)

    return ok(
        CompactionResult(
            summary=summary,
            first_kept_entry_id=first_kept_entry_id,
            tokens_before=tokens_before,
            details=CompactionDetails(read_files=read_files, modified_files=modified_files),
        )
    )


async def _generate_turn_prefix_summary(
    messages: list[AgentMessage],
    model: Model,
    reserve_tokens: int,
    api_key: str | None,
    headers: dict[str, str] | None = None,
    signal: Any | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> Result:
    """Parity: ``generateTurnPrefixSummary`` — half the reserve, not 80%."""
    computed = math.floor(0.5 * reserve_tokens)
    max_tokens = min(computed, model.max_tokens) if model.max_tokens > 0 else computed
    llm_messages = convert_to_llm(messages)
    conversation_text = serialize_conversation(llm_messages)
    prompt_text = (
        f"<conversation>\n{conversation_text}\n</conversation>\n\n"
        f"{_TURN_PREFIX_SUMMARIZATION_PROMPT}"
    )
    return await _run_summarization_completion(
        prompt_text=prompt_text,
        model=model,
        max_tokens=max_tokens,
        api_key=api_key,
        headers=headers,
        signal=signal,
        thinking_level=thinking_level,
        stream_fn=stream_fn,
        runtime=runtime,
        error_label="Turn prefix summarization",
    )


# ---------------------------------------------------------------------------
# Multi-stage summarisation (port of compaction.ts summarizeInStages etc.)
# ---------------------------------------------------------------------------

#: Maximum consecutive generic-fallback results before the circuit opens.
#: Parity: ``MAX_CONSECUTIVE_GENERIC_FALLBACKS``.
MAX_CONSECUTIVE_GENERIC_FALLBACKS: int = 2

#: Default summary text when there is no prior history to summarise.
#: Parity: ``DEFAULT_SUMMARY_FALLBACK``.
DEFAULT_SUMMARY_FALLBACK: str = "No prior history."

#: Identifier-preservation clause injected into summarisation prompts.
#: Parity: ``IDENTIFIER_PRESERVATION_INSTRUCTIONS``.
IDENTIFIER_PRESERVATION_INSTRUCTIONS: str = (
    "Preserve all opaque identifiers exactly as written (no shortening or "
    "reconstruction), including UUIDs, hashes, IDs, hostnames, IPs, ports, "
    "URLs, and file names."
)

_MERGE_SUMMARIES_INSTRUCTIONS: str = "\n".join(
    [
        "Merge these partial summaries into a single cohesive summary.",
        "",
        "MUST PRESERVE:",
        "- Active tasks and their current status (in-progress, blocked, pending)",
        "- Batch operation progress (e.g., '5/17 items completed')",
        "- The last thing the user requested and what was being done about it",
        "- Decisions made and their rationale",
        "- TODOs, open questions, and constraints",
        "- Any commitments or follow-ups promised",
        "",
        "PRIORITIZE recent context over older history. The agent needs to know",
        "what it was doing, not just what was discussed.",
    ]
)

# Discriminated-union result for staged summarisation.
# Parity: ``CompactionSummaryResult``.
CompactionSummaryResultKind = Literal["summary", "generic-fallback"]


@dataclass(frozen=True)
class CompactionSummaryResult:
    """Result of one compaction summarisation attempt.

    Parity: ``CompactionSummaryResult``.
    ``kind == "generic-fallback"`` means the result is a placeholder, not a
    real summary; callers should track how many consecutive fallbacks occur.
    """

    kind: CompactionSummaryResultKind = "summary"
    text: str = ""


# Identifier policy for summarisation instructions.
CompactionIdentifierPolicy = Literal["strict", "off", "custom"]


def _resolve_identifier_preservation_instructions(
    identifier_policy: CompactionIdentifierPolicy = "strict",
    identifier_instructions: str | None = None,
) -> str | None:
    """Return the identifier-preservation clause for a summarisation prompt.

    Parity: ``resolveIdentifierPreservationInstructions``.
    """
    if identifier_policy == "off":
        return None
    if identifier_policy == "custom":
        custom = (identifier_instructions or "").strip()
        return custom if custom else IDENTIFIER_PRESERVATION_INSTRUCTIONS
    return IDENTIFIER_PRESERVATION_INSTRUCTIONS


def _build_compaction_summarization_instructions(
    custom_instructions: str | None = None,
    identifier_policy: CompactionIdentifierPolicy = "strict",
    identifier_instructions: str | None = None,
) -> str | None:
    """Join identifier-preservation and caller-supplied instructions.

    Parity: ``buildCompactionSummarizationInstructions``.
    """
    custom = (custom_instructions or "").strip() or None
    id_preservation = _resolve_identifier_preservation_instructions(
        identifier_policy, identifier_instructions
    )
    if not id_preservation and not custom:
        return None
    if not custom:
        return id_preservation
    if not id_preservation:
        return f"Additional focus:\n{custom}"
    return f"{id_preservation}\n\nAdditional focus:\n{custom}"


def resolve_context_window_tokens(model: Model | None = None) -> int:
    """Return a positive context-window token count from model metadata.

    Parity: ``resolveContextWindowTokens``.
    """
    # Parity: DEFAULT_CONTEXT_TOKENS from agents/defaults.ts = 200_000.
    _DEFAULT_CONTEXT_TOKENS = 200_000

    effective = getattr(model, "context_tokens", None) or getattr(model, "context_window", None)
    return max(1, math.floor(effective if effective else _DEFAULT_CONTEXT_TOKENS))


def _extract_chunk_time_range(chunk: list[AgentMessage]) -> str:
    """Return a compact ISO timestamp range string for merge metadata.

    Parity: ``extractChunkTimeRange``.
    """
    import datetime

    earliest: int | None = None
    latest: int | None = None
    for message in chunk:
        ts = getattr(message, "timestamp", None)
        if not isinstance(ts, (int, float)) or ts <= 0 or not math.isfinite(ts):
            continue
        ts = int(ts)
        earliest = ts if earliest is None else min(earliest, ts)
        latest = ts if latest is None else max(latest, ts)
    if earliest is None or latest is None:
        return ""

    def _fmt(ts: int) -> str:
        return datetime.datetime.fromtimestamp(ts / 1000, tz=datetime.timezone.utc).strftime(
            "%Y-%m-%d %H:%M"
        )

    r = _fmt(earliest) if earliest == latest else f"{_fmt(earliest)} - {_fmt(latest)}"
    return f" [{r} UTC]"


async def _summarize_chunks_staged(
    *,
    messages: list[AgentMessage],
    model: Model,
    api_key: str | None,
    headers: dict[str, Any] | None = None,
    signal: Any | None = None,
    reserve_tokens: int,
    max_chunk_tokens: int,
    custom_instructions: str | None = None,
    identifier_policy: CompactionIdentifierPolicy = "strict",
    identifier_instructions: str | None = None,
    previous_summary: str | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> str:
    """Summarise *messages* in at most ``max_chunk_tokens``-sized chunks.

    Parity: ``summarizeChunks``.
    """
    from .compaction_planning import build_summary_chunks

    if not messages:
        return previous_summary or DEFAULT_SUMMARY_FALLBACK

    chunks = build_summary_chunks(messages, max_chunk_tokens)
    effective_instructions = _build_compaction_summarization_instructions(
        custom_instructions, identifier_policy, identifier_instructions
    )
    summary = previous_summary
    has_generated_chunk = False

    for chunk_index, chunk in enumerate(chunks):
        result = await generate_summary(
            chunk,
            model,
            reserve_tokens,
            api_key,
            headers,
            signal,
            effective_instructions,
            summary,
            thinking_level,
            stream_fn,
            runtime,
        )
        if isinstance(result, Err):
            if not has_generated_chunk:
                return err(result.error).error.message
            # Partial failure — return best-effort partial summary.
            completed = chunk_index
            total = len(chunks)
            suffix = (
                f"\n\n[Partial summary: chunks 1-{completed} of {total} were summarized. "
                f"Chunks {completed + 1}-{total} could not be processed.]"
            )
            return (summary or DEFAULT_SUMMARY_FALLBACK) + suffix
        summary = result.value
        has_generated_chunk = True

    return summary or DEFAULT_SUMMARY_FALLBACK


async def _summarize_with_fallback_result(
    *,
    messages: list[AgentMessage],
    model: Model,
    api_key: str | None,
    headers: dict[str, Any] | None = None,
    signal: Any | None = None,
    reserve_tokens: int,
    max_chunk_tokens: int,
    context_window: int,
    custom_instructions: str | None = None,
    identifier_policy: CompactionIdentifierPolicy = "strict",
    identifier_instructions: str | None = None,
    previous_summary: str | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> CompactionSummaryResult:
    """Summarise with progressive fallback for oversized messages.

    Parity: ``summarizeWithFallbackResult``.
    """
    from .compaction_planning import build_oversized_fallback_plan

    if not messages:
        return CompactionSummaryResult(
            kind="summary", text=previous_summary or DEFAULT_SUMMARY_FALLBACK
        )

    # Attempt full summarisation first.
    partial_fallback: str | None = None
    try:
        text = await _summarize_chunks_staged(
            messages=messages,
            model=model,
            api_key=api_key,
            headers=headers,
            signal=signal,
            reserve_tokens=reserve_tokens,
            max_chunk_tokens=max_chunk_tokens,
            custom_instructions=custom_instructions,
            identifier_policy=identifier_policy,
            identifier_instructions=identifier_instructions,
            previous_summary=previous_summary,
            thinking_level=thinking_level,
            stream_fn=stream_fn,
            runtime=runtime,
        )
        return CompactionSummaryResult(kind="summary", text=text)
    except Exception as full_err:
        partial_fallback = getattr(full_err, "partial_summary", None)

    # Fallback: summarise only small messages, note oversized ones.
    plan = build_oversized_fallback_plan(messages, context_window)
    if plan.small_messages and len(plan.small_messages) != len(messages):
        try:
            partial_text = await _summarize_chunks_staged(
                messages=plan.small_messages,
                model=model,
                api_key=api_key,
                headers=headers,
                signal=signal,
                reserve_tokens=reserve_tokens,
                max_chunk_tokens=max_chunk_tokens,
                custom_instructions=custom_instructions,
                identifier_policy=identifier_policy,
                identifier_instructions=identifier_instructions,
                previous_summary=previous_summary,
                thinking_level=thinking_level,
                stream_fn=stream_fn,
                runtime=runtime,
            )
            notes = "\n\n" + "\n".join(plan.oversized_notes) if plan.oversized_notes else ""
            return CompactionSummaryResult(kind="summary", text=partial_text + notes)
        except Exception as partial_err:
            retry_partial = getattr(partial_err, "partial_summary", None)
            if retry_partial:
                notes = "\n\n" + "\n".join(plan.oversized_notes) if plan.oversized_notes else ""
                partial_fallback = retry_partial + notes

    if partial_fallback:
        return CompactionSummaryResult(kind="summary", text=partial_fallback)

    return CompactionSummaryResult(
        kind="generic-fallback",
        text=(
            f"Context contained {len(messages)} messages "
            f"({len(plan.oversized_notes)} oversized). "
            "Summary unavailable due to size limits."
        ),
    )


async def summarize_in_stages(
    messages: list[AgentMessage],
    model: Model,
    api_key: str | None,
    headers: dict[str, Any] | None = None,
    signal: Any | None = None,
    reserve_tokens: int = 16384,
    max_chunk_tokens: int = 50_000,
    context_window: int = 200_000,
    custom_instructions: str | None = None,
    identifier_policy: CompactionIdentifierPolicy = "strict",
    identifier_instructions: str | None = None,
    previous_summary: str | None = None,
    parts: int | None = None,
    min_messages_for_split: int | None = None,
    thinking_level: Optional[ThinkingLevel] = None,
    stream_fn: StreamFn | None = None,
    runtime: AgentCoreCompletionRuntimeDeps | None = None,
) -> CompactionSummaryResult:
    """Summarise history in multiple stages when a single pass is too large.

    Parity: ``summarizeInStages``.

    When history exceeds ``max_chunk_tokens`` a split plan is built and each
    chunk is summarised independently.  A circuit-breaker aborts after
    :data:`MAX_CONSECUTIVE_GENERIC_FALLBACKS` consecutive placeholder results
    so the caller keeps the original transcript instead of committing an
    incomplete summary.

    Args:
        messages: Messages to summarise (older portion of the transcript).
        model: LLM to use for summarisation.
        api_key: Provider API key.
        headers: Optional extra HTTP headers.
        signal: Optional cancellation signal.
        reserve_tokens: Token budget reserved for the summary output.
        max_chunk_tokens: Maximum tokens per summarisation chunk.
        context_window: Full model context window in tokens.
        custom_instructions: Additional user-supplied focus text.
        identifier_policy: ``"strict"`` (default), ``"off"``, or ``"custom"``.
        identifier_instructions: Custom identifier clause (``policy=="custom"`` only).
        previous_summary: Prior compaction summary to update incrementally.
        parts: Number of split parts to attempt (defaults to 2).
        min_messages_for_split: Minimum message count before splitting.
        thinking_level: Reasoning level override.
        stream_fn: Optional streaming callback.
        runtime: Optional runtime dependency injection.

    Returns:
        :class:`CompactionSummaryResult` with ``kind`` and ``text``.
    """
    from .compaction_planning import build_stage_split_plan, StageSplitPlanSingle

    if not messages:
        return CompactionSummaryResult(
            kind="summary", text=previous_summary or DEFAULT_SUMMARY_FALLBACK
        )

    plan = build_stage_split_plan(
        messages,
        max_chunk_tokens=max_chunk_tokens,
        parts=parts,
        min_messages_for_split=min_messages_for_split,
    )

    if isinstance(plan, StageSplitPlanSingle):
        return await _summarize_with_fallback_result(
            messages=messages,
            model=model,
            api_key=api_key,
            headers=headers,
            signal=signal,
            reserve_tokens=reserve_tokens,
            max_chunk_tokens=max_chunk_tokens,
            context_window=context_window,
            custom_instructions=custom_instructions,
            identifier_policy=identifier_policy,
            identifier_instructions=identifier_instructions,
            previous_summary=previous_summary,
            thinking_level=thinking_level,
            stream_fn=stream_fn,
            runtime=runtime,
        )

    # Multi-chunk staged summarisation with circuit-breaker.
    partial_summaries: list[str] = []
    consecutive_generic_fallbacks = 0
    oldest_chunk_degraded = False

    for index, chunk in enumerate(plan.chunks):
        result = await _summarize_with_fallback_result(
            messages=chunk,
            model=model,
            api_key=api_key,
            headers=headers,
            signal=signal,
            reserve_tokens=reserve_tokens,
            max_chunk_tokens=max_chunk_tokens,
            context_window=context_window,
            custom_instructions=custom_instructions,
            identifier_policy=identifier_policy,
            identifier_instructions=identifier_instructions,
            previous_summary=None,  # Chunks summarised independently.
            thinking_level=thinking_level,
            stream_fn=stream_fn,
            runtime=runtime,
        )
        consecutive_generic_fallbacks = (
            consecutive_generic_fallbacks + 1 if result.kind == "generic-fallback" else 0
        )
        if index == 0:
            oldest_chunk_degraded = result.kind == "generic-fallback"

        # Circuit-breaker: abort before committing a gap.
        if consecutive_generic_fallbacks >= MAX_CONSECUTIVE_GENERIC_FALLBACKS:
            raise RuntimeError(
                "Compaction staged summarization stopped after repeated generic fallbacks"
            )

        partial_summaries.append(result.text)

    # Single surviving chunk.
    if len(partial_summaries) == 1:
        return CompactionSummaryResult(
            kind="generic-fallback" if oldest_chunk_degraded else "summary",
            text=partial_summaries[0],
        )

    # Merge partial summaries via a final summarisation call.
    now = int(time.time() * 1000)
    # Build synthetic user messages so the merge call sees chronological chunks.
    summary_messages: list[AgentMessage] = []
    for idx, summary_text in enumerate(partial_summaries):
        chunk = plan.chunks[idx]
        time_range = _extract_chunk_time_range(chunk)
        total = len(partial_summaries)
        if idx == 0:
            label = f"[Chunk 1 - oldest messages{time_range}]"
        elif idx == total - 1:
            label = f"[Chunk {total} - most recent messages{time_range}]"
        else:
            label = f"[Chunk {idx + 1}/{total}{time_range}]"

        summary_messages.append(
            as_agent_message(
                UserMessage(
                    content=[TextContent(text=f"{label}\n{summary_text}")],
                    timestamp=now - (total - 1 - idx),
                )
            )
        )

    custom = (custom_instructions or "").strip()
    merge_instructions = (
        f"{_MERGE_SUMMARIES_INSTRUCTIONS}\n\n{custom}" if custom else _MERGE_SUMMARIES_INSTRUCTIONS
    )

    merged = await _summarize_with_fallback_result(
        messages=summary_messages,
        model=model,
        api_key=api_key,
        headers=headers,
        signal=signal,
        reserve_tokens=reserve_tokens,
        max_chunk_tokens=max_chunk_tokens,
        context_window=context_window,
        custom_instructions=merge_instructions,
        identifier_policy=identifier_policy,
        identifier_instructions=identifier_instructions,
        previous_summary=None,
        thinking_level=thinking_level,
        stream_fn=stream_fn,
        runtime=runtime,
    )
    if oldest_chunk_degraded and merged.kind == "summary":
        return CompactionSummaryResult(kind="generic-fallback", text=merged.text)
    return merged


__all__ = [
    "CompactionDetails",
    "CompactionPreparation",
    "CompactionResult",
    "CompactionSettings",
    "CompactionSummaryResult",
    "ContextUsageEstimate",
    "DEFAULT_COMPACTION_SETTINGS",
    "DEFAULT_SUMMARY_FALLBACK",
    "IDENTIFIER_PRESERVATION_INSTRUCTIONS",
    "MAX_CONSECUTIVE_GENERIC_FALLBACKS",
    "SUMMARIZATION_SYSTEM_PROMPT",
    "calculate_context_tokens",
    "compact",
    "estimate_context_tokens",
    "estimate_tokens",
    "find_cut_point",
    "find_turn_start_index",
    "generate_summary",
    "get_last_assistant_usage",
    "prepare_compaction",
    "resolve_context_window_tokens",
    "serialize_conversation",
    "should_compact",
    "summarize_in_stages",
]

# Parity: compaction.ts re-exports serializeConversation from utils.ts.
from .compaction_utils import serialize_conversation  # noqa: E402,F811
