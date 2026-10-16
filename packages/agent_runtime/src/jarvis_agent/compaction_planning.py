"""Compaction planning helpers: token estimation, chunk strategy, history pruning.

Port of ``src/agents/compaction-planning.ts``.

All functions here are pure / deterministic — no LLM calls. They plan *how*
to split a message list for summarisation and whether to prune older history
to keep the context window healthy.

Signatures follow the TS order so call-sites read the same against either
codebase. The worker-thread variants (``buildStageSplitPlanWithWorker``, etc.)
are collapsed into direct calls — Python has no worker-thread penalty here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import AgentMessage

# ---------------------------------------------------------------------------
# Constants (parity: compaction-planning.ts top-level exports)
# ---------------------------------------------------------------------------

#: Default share of context window targeted for each compaction chunk.
#: Parity: ``BASE_CHUNK_RATIO``.
BASE_CHUNK_RATIO: float = 0.4

#: Lower bound for adaptive compaction chunk sizing.
#: Parity: ``MIN_CHUNK_RATIO``.
MIN_CHUNK_RATIO: float = 0.15

#: Safety multiplier for token-estimate inaccuracy.
#: Parity: ``SAFETY_MARGIN``.
SAFETY_MARGIN: float = 1.2

#: Overhead tokens reserved for the summary prompt, system prompt, prior
#: summary, wrapper tags, and high-reasoning generation.
#: Parity: ``SUMMARIZATION_OVERHEAD_TOKENS``.
SUMMARIZATION_OVERHEAD_TOKENS: int = 4096

_DEFAULT_PARTS: int = 2


# ---------------------------------------------------------------------------
# Type helpers
# ---------------------------------------------------------------------------


def _block_get(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _is_runtime_context_message(message: "AgentMessage") -> bool:
    """Runtime-context entries are invisible to the model and contribute 0 tokens.

    Parity: ``stripRuntimeContextCustomMessages`` filter predicate — any
    ``custom`` role message whose ``custom_type`` ends with the runtime-context
    suffix is model-invisible.
    """
    if getattr(message, "role", None) != "custom":
        return False
    custom_type = getattr(message, "custom_type", None) or ""
    # OpenClaw marks runtime-context messages with this suffix.
    return custom_type.endswith("runtime_context") or custom_type.endswith("runtimeContext")


def _strip_tool_result_details(messages: "list[AgentMessage]") -> "list[AgentMessage]":
    """Remove toolResult.details before token estimates or summarisation.

    Parity: ``stripToolResultDetails`` — details must never reach LLM-facing
    compaction (SECURITY constraint).
    """
    result: list[AgentMessage] = []
    for msg in messages:
        if getattr(msg, "role", None) == "toolResult":
            details = getattr(msg, "details", None)
            if details is not None:
                # Shallow-copy the message with details cleared.
                try:
                    import dataclasses

                    if dataclasses.is_dataclass(msg):
                        msg = dataclasses.replace(msg, details=None)  # type: ignore[arg-type]
                    else:
                        msg = dict(msg)  # type: ignore[assignment]
                        msg["details"] = None
                except Exception:
                    pass
        result.append(msg)
    return result


def sanitize_compaction_messages(messages: "list[AgentMessage]") -> "list[AgentMessage]":
    """Remove runtime-only context and tool-result details before estimation.

    Parity: ``sanitizeCompactionMessages``.
    Must be called before any LLM-facing summarisation or token estimate.
    """
    stripped = _strip_tool_result_details(messages)
    return [m for m in stripped if not _is_runtime_context_message(m)]


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def _estimate_single_message_tokens(message: "AgentMessage") -> int:
    """Estimate tokens for one message using the same heuristic as compaction.py.

    Parity: ``estimateTokens`` — ceil(chars / 4).
    Kept local to avoid a circular import with compaction.py; callers here
    only need the planning layer's estimate, not the full compaction module.
    """
    IMAGE_BLOCK_CHARS = 4800

    def _block_text(block: Any) -> str:
        block_type = _block_get(block, "type")
        text = _block_get(block, "text")
        if block_type == "text" and text:
            return str(text)
        if block_type in ("toolResult", "tool_result"):
            if text:
                return str(text)
            content = _block_get(block, "content")
            return str(content) if isinstance(content, str) else ""
        return ""

    chars = 0
    role = getattr(message, "role", None)

    if role == "user":
        content = getattr(message, "content", None)
        if isinstance(content, str):
            chars = len(content)
        elif isinstance(content, list):
            for block in content:
                if _block_get(block, "type") == "image":
                    chars += IMAGE_BLOCK_CHARS
                else:
                    chars += len(_block_text(block))
        return math.ceil(chars / 4)

    if role == "assistant":
        content = getattr(message, "content", None) or []
        for block in content:
            block_type = _block_get(block, "type")
            if block_type == "text":
                chars += len(_block_get(block, "text") or "")
            elif block_type == "thinking":
                chars += len(_block_get(block, "thinking") or "")
            elif block_type == "toolCall":
                import json

                args = _block_get(block, "arguments") or {}
                try:
                    args_str = json.dumps(args, separators=(",", ":"), ensure_ascii=False)
                except Exception:
                    args_str = "[unserializable]"
                chars += len(_block_get(block, "name") or "") + len(args_str)
        return math.ceil(chars / 4)

    if role in ("custom", "toolResult"):
        content = getattr(message, "content", None)
        if isinstance(content, str):
            chars = len(content)
        elif isinstance(content, list):
            for block in content:
                if _block_get(block, "type") == "image":
                    chars += IMAGE_BLOCK_CHARS
                else:
                    chars += len(_block_text(block))
        return math.ceil(chars / 4)

    if role == "bashExecution":
        chars = len(getattr(message, "command", "") or "") + len(
            getattr(message, "output", "") or ""
        )
        return math.ceil(chars / 4)

    if role in ("branchSummary", "compactionSummary"):
        chars = len(getattr(message, "summary", "") or "")
        return math.ceil(chars / 4)

    return 0


def estimate_messages_tokens(messages: "list[AgentMessage]") -> int:
    """Estimate token count for a sanitized message list.

    Parity: ``estimateMessagesTokens``.
    SECURITY: strips toolResult.details and runtime-context entries first.
    """
    safe = sanitize_compaction_messages(messages)
    return sum(_estimate_single_message_tokens(m) for m in safe)


def _estimate_per_message_tokens(messages: "list[AgentMessage]") -> list[int]:
    """Per-original-message token estimates, aligned 1:1 to the input array.

    Parity: ``estimatePerMessageTokens``.
    Runtime-context entries estimate to 0 (they are model-invisible).
    """
    detail_stripped = _strip_tool_result_details(messages)
    model_visible: set[int] = {id(m) for m in detail_stripped if not _is_runtime_context_message(m)}
    return [
        _estimate_single_message_tokens(m) if id(m) in model_visible else 0 for m in detail_stripped
    ]


# ---------------------------------------------------------------------------
# Chunk helpers
# ---------------------------------------------------------------------------


def _normalize_compaction_parts(parts: int, message_count: int) -> int:
    """Clamp requested split parts to a usable count.

    Parity: ``normalizeCompactionParts``.
    """
    if not math.isfinite(parts) or parts <= 1:
        return 1
    return min(max(1, math.floor(parts)), max(1, message_count))


def _split_messages_by_token_share(
    messages: "list[AgentMessage]",
    parts: int = _DEFAULT_PARTS,
) -> "list[list[AgentMessage]]":
    """Split messages into roughly equal token-share chunks.

    Parity: ``splitMessagesByTokenShare``.
    Never separates active tool-use / tool-result pairs.
    """
    if not messages:
        return []
    normalized_parts = _normalize_compaction_parts(parts, len(messages))
    if normalized_parts <= 1:
        return [messages]

    per_message = _estimate_per_message_tokens(messages)
    total = sum(per_message)
    target_per_chunk = max(1, total // normalized_parts)

    # Effective max per chunk — allows one oversized message to flush its chunk
    # without infinite growth.
    effective_max = target_per_chunk * 2

    chunks: list[list[AgentMessage]] = []
    current_chunk: list[AgentMessage] = []
    current_tokens = 0

    for message, message_tokens in zip(messages, per_message):
        # Start a new chunk when we'd exceed the target and already have content.
        if current_chunk and current_tokens + message_tokens > target_per_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

        current_chunk.append(message)
        current_tokens += message_tokens

        # Split oversized messages immediately to bound chunk growth.
        if message_tokens > effective_max:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _chunk_messages_by_max_tokens(
    messages: "list[AgentMessage]",
    max_chunk_tokens: int,
) -> "list[list[AgentMessage]]":
    """Split messages into chunks where each is at most *max_chunk_tokens*.

    Parity: ``chunkMessagesByMaxTokens`` — used by ``buildSummaryChunks``.
    """
    if not messages:
        return []

    chunks: list[list[AgentMessage]] = []
    current_chunk: list[AgentMessage] = []
    current_tokens = 0

    for msg in messages:
        msg_tokens = _estimate_single_message_tokens(msg)
        if current_chunk and current_tokens + msg_tokens > max_chunk_tokens:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0
        current_chunk.append(msg)
        current_tokens += msg_tokens

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# ---------------------------------------------------------------------------
# Adaptive chunk ratio
# ---------------------------------------------------------------------------


def compute_adaptive_chunk_ratio(
    messages: "list[AgentMessage]",
    context_window: int,
) -> float:
    """Compute adaptive chunk ratio based on average message size.

    When messages are large, use smaller chunks to avoid exceeding model limits.
    Parity: ``computeAdaptiveChunkRatio``.
    """
    if not messages:
        return BASE_CHUNK_RATIO

    total_tokens = estimate_messages_tokens(messages)
    avg_tokens = total_tokens / len(messages)

    # Apply SAFETY_MARGIN to account for estimation inaccuracy.
    safe_avg_tokens = avg_tokens * SAFETY_MARGIN
    avg_ratio = safe_avg_tokens / max(1, context_window)

    # If average message > 10% of context, reduce chunk ratio.
    if avg_ratio > 0.1:
        reduction = min(avg_ratio * 2, BASE_CHUNK_RATIO - MIN_CHUNK_RATIO)
        return max(MIN_CHUNK_RATIO, BASE_CHUNK_RATIO - reduction)

    return BASE_CHUNK_RATIO


# ---------------------------------------------------------------------------
# Oversized check
# ---------------------------------------------------------------------------


def is_oversized_for_summary(message: "AgentMessage", context_window: int) -> bool:
    """Return True if a single message is too large to summarize safely.

    Single message > 50% of context cannot be summarized safely.
    Parity: ``isOversizedForSummary``.
    """
    tokens = _estimate_single_message_tokens(message) * SAFETY_MARGIN
    return tokens > context_window * 0.5


# ---------------------------------------------------------------------------
# Summary chunk builder
# ---------------------------------------------------------------------------


def build_summary_chunks(
    messages: "list[AgentMessage]",
    max_chunk_tokens: int,
) -> "list[list[AgentMessage]]":
    """Build sanitized chunks for summarization prompts.

    Parity: ``buildSummaryChunks``.
    SECURITY: never feeds toolResult.details into summarization.
    """
    safe_messages = sanitize_compaction_messages(messages)
    return _chunk_messages_by_max_tokens(safe_messages, max_chunk_tokens)


# ---------------------------------------------------------------------------
# Oversized fallback plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OversizedFallbackPlan:
    """Messages safe to summarize plus notes for oversized ones.

    Parity: ``OversizedFallbackPlan``.
    """

    small_messages: list[Any] = field(default_factory=list)
    oversized_notes: list[str] = field(default_factory=list)


def build_oversized_fallback_plan(
    messages: "list[AgentMessage]",
    context_window: int,
) -> OversizedFallbackPlan:
    """Separate oversized messages and emit compact placeholder notes.

    Parity: ``buildOversizedFallbackPlan``.
    """
    small_messages: list[AgentMessage] = []
    oversized_notes: list[str] = []

    per_message_tokens = _estimate_per_message_tokens(messages)
    oversized_threshold = context_window * 0.5

    for index, msg in enumerate(messages):
        tokens = per_message_tokens[index]
        if tokens * SAFETY_MARGIN > oversized_threshold:
            role = getattr(msg, "role", None) or "message"
            oversized_notes.append(
                f"[Large {role} (~{round(tokens / 1000)}K tokens) omitted from summary]"
            )
        else:
            small_messages.append(msg)

    return OversizedFallbackPlan(small_messages=small_messages, oversized_notes=oversized_notes)


# ---------------------------------------------------------------------------
# Stage split plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StageSplitPlanSingle:
    """Single-chunk plan — no splitting needed. Parity: ``{mode: "single"}``."""

    mode: str = "single"


@dataclass(frozen=True)
class StageSplitPlanSplit:
    """Multi-chunk plan. Parity: ``{mode: "split", chunks: ...}``."""

    mode: str = "split"
    chunks: list[Any] = field(default_factory=list)


StageSplitPlan = StageSplitPlanSingle | StageSplitPlanSplit


def build_stage_split_plan(
    messages: "list[AgentMessage]",
    max_chunk_tokens: int,
    parts: int | None = None,
    min_messages_for_split: int | None = None,
) -> StageSplitPlan:
    """Decide whether to split a summarisation stage into chunks.

    Parity: ``buildStageSplitPlan``.
    """
    effective_min = max(2, min_messages_for_split if min_messages_for_split is not None else 4)
    effective_parts = _normalize_compaction_parts(
        parts if parts is not None else _DEFAULT_PARTS, len(messages)
    )
    total_tokens = estimate_messages_tokens(messages)

    if effective_parts <= 1 or len(messages) < effective_min or total_tokens <= max_chunk_tokens:
        return StageSplitPlanSingle()

    chunks = [c for c in _split_messages_by_token_share(messages, effective_parts) if c]
    if len(chunks) > 1:
        return StageSplitPlanSplit(chunks=chunks)
    return StageSplitPlanSingle()


# ---------------------------------------------------------------------------
# History prune plan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryPruneResult:
    """Result of dropping oldest chunks from the summarizable history.

    Parity: return type of ``pruneHistoryForContextShare``.
    """

    messages: list[Any] = field(default_factory=list)
    dropped_messages_list: list[Any] = field(default_factory=list)
    dropped_chunks: int = 0
    dropped_messages: int = 0
    dropped_tokens: int = 0
    kept_tokens: int = 0
    budget_tokens: int = 0


@dataclass(frozen=True)
class HistoryPrunePlan:
    """Token accounting and optional prune result for context-window headroom.

    Parity: ``HistoryPrunePlan``.
    """

    summarizable_tokens: int = 0
    new_content_tokens: int = 0
    max_history_tokens: int = 0
    pruned: HistoryPruneResult | None = None


def _repair_tool_use_result_pairing(
    messages: "list[AgentMessage]",
) -> "tuple[list[AgentMessage], int]":
    """Drop orphaned tool-result messages after their tool-use was dropped.

    Parity: ``repairToolUseResultPairing``.
    Returns ``(repaired_messages, orphan_count)``.
    """
    # Collect all tool-call ids present in assistant messages.
    live_tool_call_ids: set[str] = set()
    for msg in messages:
        if getattr(msg, "role", None) != "assistant":
            continue
        for block in getattr(msg, "content", None) or []:
            if _block_get(block, "type") == "toolCall":
                call_id = _block_get(block, "id") or _block_get(block, "tool_call_id")
                if call_id:
                    live_tool_call_ids.add(str(call_id))

    repaired: list[AgentMessage] = []
    orphan_count = 0
    for msg in messages:
        if getattr(msg, "role", None) == "toolResult":
            tool_call_id = getattr(msg, "tool_call_id", None) or getattr(msg, "toolCallId", None)
            if tool_call_id and str(tool_call_id) not in live_tool_call_ids:
                orphan_count += 1
                continue  # drop orphan
        repaired.append(msg)

    return repaired, orphan_count


def _prune_history_for_context_share(
    messages: "list[AgentMessage]",
    max_context_tokens: int,
    max_history_share: float | None = None,
    parts: int | None = None,
    mode: str = "share",
) -> HistoryPruneResult:
    """Drop oldest token-share chunks until history fits the context budget.

    Parity: ``pruneHistoryForContextShare``.
    """
    is_handoff = mode == "handoff"
    default_share = 0.2 if is_handoff else 0.5
    effective_share = max_history_share if max_history_share is not None else default_share
    budget_tokens = max(1, math.floor(max_context_tokens * effective_share))

    kept_messages = list(messages)
    all_dropped: list[AgentMessage] = []
    dropped_chunks = 0
    dropped_messages_count = 0
    dropped_tokens = 0

    effective_parts = parts if parts is not None else _DEFAULT_PARTS

    while kept_messages and estimate_messages_tokens(kept_messages) > budget_tokens:
        chunks = _split_messages_by_token_share(kept_messages, effective_parts)
        if len(chunks) <= 1:
            break
        dropped, *rest = chunks
        if not dropped:
            break
        flat_rest = [m for chunk in rest for m in chunk]

        # Repair orphaned tool-results after dropping the oldest chunk.
        repaired_kept, orphan_count = _repair_tool_use_result_pairing(flat_rest)

        dropped_chunks += 1
        dropped_messages_count += len(dropped) + orphan_count
        dropped_tokens += estimate_messages_tokens(dropped)
        all_dropped.extend(dropped)
        kept_messages = repaired_kept

    return HistoryPruneResult(
        messages=kept_messages,
        dropped_messages_list=all_dropped,
        dropped_chunks=dropped_chunks,
        dropped_messages=dropped_messages_count,
        dropped_tokens=dropped_tokens,
        kept_tokens=estimate_messages_tokens(kept_messages),
        budget_tokens=budget_tokens,
    )


def build_history_prune_plan(
    messages_to_summarize: "list[AgentMessage]",
    turn_prefix_messages: "list[AgentMessage]",
    tokens_before: int,
    context_window_tokens: int,
    max_history_share: float,
    parts: int | None = None,
) -> HistoryPrunePlan:
    """Compute whether new content exceeds the history budget and plan pruning.

    Parity: ``buildHistoryPrunePlan``.
    """
    summarizable_tokens = estimate_messages_tokens(
        messages_to_summarize
    ) + estimate_messages_tokens(turn_prefix_messages)
    new_content_tokens = max(0, math.floor(tokens_before - summarizable_tokens))

    # Apply SAFETY_MARGIN so token underestimates don't trigger unnecessary pruning.
    max_history_tokens = math.floor(context_window_tokens * max_history_share * SAFETY_MARGIN)

    if new_content_tokens <= max_history_tokens:
        return HistoryPrunePlan(
            summarizable_tokens=summarizable_tokens,
            new_content_tokens=new_content_tokens,
            max_history_tokens=max_history_tokens,
        )

    pruned = _prune_history_for_context_share(
        messages=messages_to_summarize,
        max_context_tokens=context_window_tokens,
        max_history_share=max_history_share,
        parts=parts,
    )
    return HistoryPrunePlan(
        summarizable_tokens=summarizable_tokens,
        new_content_tokens=new_content_tokens,
        max_history_tokens=max_history_tokens,
        pruned=pruned,
    )


__all__ = [
    "BASE_CHUNK_RATIO",
    "MIN_CHUNK_RATIO",
    "SAFETY_MARGIN",
    "SUMMARIZATION_OVERHEAD_TOKENS",
    "OversizedFallbackPlan",
    "StageSplitPlan",
    "StageSplitPlanSingle",
    "StageSplitPlanSplit",
    "HistoryPrunePlan",
    "HistoryPruneResult",
    "build_history_prune_plan",
    "build_oversized_fallback_plan",
    "build_stage_split_plan",
    "build_summary_chunks",
    "compute_adaptive_chunk_ratio",
    "estimate_messages_tokens",
    "is_oversized_for_summary",
    "sanitize_compaction_messages",
]
