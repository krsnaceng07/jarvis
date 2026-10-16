"""Context pruning: soft-trim + hard-clear tool result pruning.

Port of ``src/agents/agent-hooks/context-pruning/pruner.ts``.

This is a lighter-weight complement to compaction.  Pruning runs per-request,
in-memory, and is **not** saved to the transcript.  It trims old large tool
results to keep the context under the model's window limit when full
compaction is not yet needed.

Two tiers:
- **Soft-trim** (``soft_trim_ratio``): keep ``head_chars + tail_chars`` of
  each large tool result; drop the middle.
- **Hard-clear** (``hard_clear_ratio``): replace eligible tool results with a
  fixed placeholder string (e.g. ``"[tool result cleared]"``).

Bootstrap safety: nothing before the first user message is ever pruned —
identity reads (SOUL.md, USER.md, etc.) happen there and must survive.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .types import AgentMessage

# ---------------------------------------------------------------------------
# Constants (parity: pruner.ts)
# ---------------------------------------------------------------------------

#: Characters-per-token estimate (same heuristic as compaction.py).
CHARS_PER_TOKEN_ESTIMATE: int = 4

#: Flat character estimate for image blocks during pruning estimation.
IMAGE_CHAR_ESTIMATE: int = 8_000

#: Placeholder written when a tool result is image-replaced during pruning.
PRUNED_CONTEXT_IMAGE_MARKER: str = "[image removed during context pruning]"


# ---------------------------------------------------------------------------
# Settings dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SoftTrimSettings:
    """Parameters for soft-trimming large tool results.

    Parity: the inline ``settings.softTrim`` shape.
    """

    #: Maximum characters before soft-trim kicks in for this result.
    max_chars: int = 10_000
    #: Characters to keep from the head of the result.
    head_chars: int = 2_000
    #: Characters to keep from the tail of the result.
    tail_chars: int = 2_000


@dataclass(frozen=True)
class HardClearSettings:
    """Parameters for hard-clearing tool results under extreme pressure.

    Parity: the inline ``settings.hardClear`` shape.
    """

    enabled: bool = True
    placeholder: str = "[tool result cleared to save context]"


#: Default tool names that are eligible for pruning.
DEFAULT_PRUNABLE_TOOLS: frozenset[str] = frozenset(
    {"read", "list_directory", "bash", "execute", "shell", "run_command"}
)


@dataclass(frozen=True)
class EffectiveContextPruningSettings:
    """Merged pruning configuration used by ``prune_context_messages``.

    Parity: ``EffectiveContextPruningSettings`` from ``settings.ts``.
    """

    #: Fraction of context window at which soft-trim is triggered.
    soft_trim_ratio: float = 0.8
    #: Fraction of context window at which hard-clear is triggered.
    hard_clear_ratio: float = 0.95
    #: Protect this many most-recent assistant messages from pruning.
    keep_last_assistants: int = 2
    #: Minimum bytes of prunable tool content before we bother trimming.
    min_prunable_tool_chars: int = 512
    soft_trim: SoftTrimSettings = field(default_factory=SoftTrimSettings)
    hard_clear: HardClearSettings = field(default_factory=HardClearSettings)
    #: Tool names eligible for pruning (empty → use defaults).
    tools: frozenset[str] = field(default_factory=lambda: DEFAULT_PRUNABLE_TOOLS)


#: Ready-to-use default pruning settings.
DEFAULT_CONTEXT_PRUNING_SETTINGS = EffectiveContextPruningSettings()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _block_get(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _coerce_text_block(block: Any) -> str | None:
    """Return the text content of a block if it is a text block.

    Parity: ``coerceTextBlock``.
    """
    if not block or not isinstance(block, (dict, object)):
        return None
    if _block_get(block, "type") != "text":
        return None
    text = _block_get(block, "text")
    if isinstance(text, str):
        return text
    # Malformed block — serialize to a placeholder.
    try:
        import json

        serialized = json.dumps(block)
        return serialized if isinstance(serialized, str) else "[malformed text block]"
    except Exception:
        return "[malformed text block]"


def _is_image_block(block: Any) -> bool:
    """Parity: ``isImageBlock``."""
    return (
        block is not None
        and isinstance(block, (dict, object))
        and _block_get(block, "type") == "image"
    )


def _has_image_blocks(content: list[Any]) -> bool:
    return any(_is_image_block(b) for b in content)


def _collect_text_segments(content: list[Any]) -> list[str]:
    """Collect only text-block strings from a content list.

    Parity: ``collectTextSegments``.
    """
    parts: list[str] = []
    for block in content:
        text = _coerce_text_block(block)
        if text is not None:
            parts.append(text)
    return parts


def _collect_prunable_tool_result_segments(content: list[Any]) -> list[str]:
    """Collect text+image-placeholder strings for prunable tool results.

    Parity: ``collectPrunableToolResultSegments``.
    """
    parts: list[str] = []
    for block in content:
        text = _coerce_text_block(block)
        if text is not None:
            parts.append(text)
        elif _is_image_block(block):
            parts.append(PRUNED_CONTEXT_IMAGE_MARKER)
    return parts


def _estimate_joined_text_length(parts: list[str]) -> int:
    """Parity: ``estimateJoinedTextLength`` — includes separator chars."""
    if not parts:
        return 0
    total = sum(len(p) for p in parts)
    total += max(0, len(parts) - 1)  # "\n" separators
    return total


def _slice_utf16_safe(s: str, start: int, end: int) -> str:
    """Slice *s* using UTF-16 code unit offsets (surrogate-pair aware).

    Simplified port — full implementation lives in ``jarvis_normalization_core``.
    """
    try:
        from jarvis_normalization_core.text_utility import truncate_utf16_safe  # type: ignore[import]

        return truncate_utf16_safe(s, end)[start:]
    except Exception:
        # Pure-Python fallback for environments without the package.
        out: list[str] = []
        used = 0
        for ch in s:
            cost = 2 if ord(ch) > 0xFFFF else 1
            if used >= end:
                break
            if used >= start:
                out.append(ch)
            used += cost
        return "".join(out)


def _take_head_from_joined_text(parts: list[str], max_chars: int) -> str:
    """Return the first *max_chars* characters of joined parts.

    Parity: ``takeHeadFromJoinedText``.
    """
    if max_chars <= 0 or not parts:
        return ""
    remaining = max_chars
    out_parts: list[str] = []
    for i, p in enumerate(parts):
        if remaining <= 0:
            break
        if i > 0:
            out_parts.append("\n")
            remaining -= 1
            if remaining <= 0:
                break
        if len(p) <= remaining:
            out_parts.append(p)
            remaining -= len(p)
        else:
            out_parts.append(_slice_utf16_safe(p, 0, remaining))
            remaining = 0
    return "".join(out_parts)


def _take_tail_from_joined_text(parts: list[str], max_chars: int) -> str:
    """Return the last *max_chars* characters of joined parts.

    Parity: ``takeTailFromJoinedText``.
    """
    if max_chars <= 0 or not parts:
        return ""
    joined = "\n".join(parts)
    if len(joined) <= max_chars:
        return joined
    return joined[-max_chars:]


def _estimate_message_chars(message: "AgentMessage") -> int:
    """Estimate message size in characters for pruning ratio calculations.

    Parity: ``estimateMessageChars``.
    """
    chars = 0
    role = getattr(message, "role", None)

    if role == "user":
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            for block in content:
                if _is_image_block(block):
                    chars += IMAGE_CHAR_ESTIMATE
                else:
                    text = _coerce_text_block(block)
                    if text:
                        chars += len(text)
        return chars

    if role == "assistant":
        for block in getattr(message, "content", None) or []:
            block_type = _block_get(block, "type")
            if block_type == "text":
                chars += len(_block_get(block, "text") or "")
            elif block_type == "thinking":
                chars += len(_block_get(block, "thinking") or "")
            elif block_type == "toolCall":
                import json

                args = _block_get(block, "arguments") or {}
                try:
                    chars += len(json.dumps(args))
                except Exception:
                    pass
                chars += len(_block_get(block, "name") or "")
        return chars

    if role in ("custom", "toolResult"):
        content = getattr(message, "content", None)
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            for block in content:
                if _is_image_block(block):
                    chars += IMAGE_CHAR_ESTIMATE
                else:
                    text = _coerce_text_block(block)
                    if text:
                        chars += len(text)
        return chars

    if role == "bashExecution":
        return len(getattr(message, "command", "") or "") + len(
            getattr(message, "output", "") or ""
        )

    if role in ("branchSummary", "compactionSummary"):
        return len(getattr(message, "summary", "") or "")

    return 0


def _estimate_context_chars(messages: "list[AgentMessage]") -> int:
    return sum(_estimate_message_chars(m) for m in messages)


def _drop_thinking_blocks(messages: "list[AgentMessage]") -> "list[AgentMessage]":
    """Return messages with thinking blocks removed from assistant content.

    Parity: ``dropThinkingBlocks``.
    """
    result: list[AgentMessage] = []
    for msg in messages:
        if getattr(msg, "role", None) != "assistant":
            result.append(msg)
            continue
        content = getattr(msg, "content", None) or []
        filtered = [b for b in content if _block_get(b, "type") != "thinking"]
        if len(filtered) == len(content):
            result.append(msg)
        else:
            try:
                import dataclasses

                result.append(dataclasses.replace(msg, content=filtered))  # type: ignore[arg-type]
            except Exception:
                result.append(msg)
    return result


def _make_tool_prunable_predicate(
    tools: frozenset[str],
) -> "callable[[str], bool]":
    """Build a predicate that checks if a tool name is eligible for pruning.

    Parity: ``makeToolPrunablePredicate``.
    """
    effective_tools = tools if tools else DEFAULT_PRUNABLE_TOOLS

    def predicate(tool_name: str) -> bool:
        return tool_name in effective_tools

    return predicate


def _make_text_content(text: str) -> Any:
    """Construct a plain text content block.

    Parity: ``asText``.
    """
    try:
        from jarvis_llm import TextContent

        return TextContent(text=text)
    except Exception:
        return {"type": "text", "text": text}


def _replace_content(message: "AgentMessage", new_content: list[Any]) -> "AgentMessage":
    """Return message with content replaced, preserving other fields."""
    try:
        import dataclasses

        if dataclasses.is_dataclass(message):
            return dataclasses.replace(message, content=new_content)  # type: ignore[arg-type]
    except Exception:
        pass
    try:
        return {**message, "content": new_content}  # type: ignore[return-value]
    except Exception:
        return message


# ---------------------------------------------------------------------------
# Per-message soft-trim
# ---------------------------------------------------------------------------


def _soft_trim_tool_result_message(
    msg: "AgentMessage",
    settings: EffectiveContextPruningSettings,
) -> "AgentMessage | None":
    """Soft-trim a single tool-result message.

    Returns ``None`` if no trim is needed (message already fits or
    trim would produce no savings), or the trimmed replacement message.

    Parity: ``softTrimToolResultMessage``.
    """
    content = getattr(msg, "content", None) or []
    has_images = _has_image_blocks(content)
    parts = (
        _collect_prunable_tool_result_segments(content)
        if has_images
        else _collect_text_segments(content)
    )
    raw_len = _estimate_joined_text_length(parts)

    if raw_len <= settings.soft_trim.max_chars:
        if not has_images:
            return None
        # Flatten image markers into plain text even if under the char limit.
        return _replace_content(msg, [_make_text_content("\n".join(parts))])

    head_chars = max(0, settings.soft_trim.head_chars)
    tail_chars = max(0, settings.soft_trim.tail_chars)
    if head_chars + tail_chars >= raw_len:
        if not has_images:
            return None
        return _replace_content(msg, [_make_text_content("\n".join(parts))])

    head = _take_head_from_joined_text(parts, head_chars)
    tail = _take_tail_from_joined_text(parts, tail_chars)
    trimmed = f"{head}\n...\n{tail}"
    note = (
        f"\n\n[Tool result trimmed: kept first {head_chars} chars and "
        f"last {tail_chars} chars of {raw_len} chars.]"
    )
    return _replace_content(msg, [_make_text_content(trimmed + note)])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def prune_context_messages(
    messages: "list[AgentMessage]",
    settings: EffectiveContextPruningSettings,
    context_window_tokens: int | None = None,
    context_window_tokens_override: int | None = None,
    drop_thinking_blocks_for_estimate: bool = False,
) -> "list[AgentMessage]":
    """Return a pruned message list when configured thresholds are exceeded.

    Pruning is **in-memory only** and is never persisted to the transcript.
    Returns the original list unchanged when no pruning is needed.

    Parity: ``pruneContextMessages``.

    Args:
        messages: Current ordered message list.
        settings: Effective pruning configuration.
        context_window_tokens: Model context window in tokens.
        context_window_tokens_override: Override for the window (e.g. from
            live session state).
        drop_thinking_blocks_for_estimate: Strip thinking blocks before
            computing the character ratio (matches ``dropThinkingBlocks``
            in the TS estimator path).

    Returns:
        Pruned message list, or the original list if no pruning occurred.
    """
    effective_window = context_window_tokens_override or context_window_tokens
    if not effective_window or effective_window <= 0:
        return messages

    char_window = effective_window * CHARS_PER_TOKEN_ESTIMATE
    if char_window <= 0:
        return messages

    # Identify the protected tail boundary.
    cutoff_index = _find_assistant_cutoff_index(messages, settings.keep_last_assistants)
    if cutoff_index is None:
        return messages

    # Bootstrap safety: never prune before the first user message.
    first_user_index = _find_first_user_index(messages)
    prune_start_index = first_user_index if first_user_index is not None else len(messages)

    is_tool_prunable = _make_tool_prunable_predicate(settings.tools)

    estimated_messages = (
        _drop_thinking_blocks(messages) if drop_thinking_blocks_for_estimate else messages
    )

    total_chars_before = _estimate_context_chars(estimated_messages)
    total_chars = total_chars_before
    ratio = total_chars / char_window

    if ratio < settings.soft_trim_ratio:
        return messages  # Nothing to do.

    prunable_tool_indexes: list[int] = []
    next_messages: list[AgentMessage] | None = None

    # --- Soft-trim pass ------------------------------------------------
    for i in range(prune_start_index, cutoff_index):
        msg = messages[i]
        if getattr(msg, "role", None) != "toolResult":
            continue
        tool_name = getattr(msg, "tool_name", None) or getattr(msg, "toolName", None) or ""
        if not is_tool_prunable(str(tool_name)):
            continue
        prunable_tool_indexes.append(i)

        updated = _soft_trim_tool_result_message(msg, settings)
        if updated is None:
            continue

        before_chars = _estimate_message_chars(msg)
        after_chars = _estimate_message_chars(updated)
        total_chars += after_chars - before_chars
        if next_messages is None:
            next_messages = list(messages)
        next_messages[i] = updated

    output_after_soft_trim = next_messages if next_messages is not None else messages
    ratio = total_chars / char_window

    if ratio < settings.hard_clear_ratio:
        return output_after_soft_trim

    if not settings.hard_clear.enabled:
        return output_after_soft_trim

    # --- Hard-clear eligibility check ----------------------------------
    prunable_tool_chars = 0
    for i in prunable_tool_indexes:
        msg = output_after_soft_trim[i]
        if getattr(msg, "role", None) == "toolResult":
            prunable_tool_chars += _estimate_message_chars(msg)

    if prunable_tool_chars < settings.min_prunable_tool_chars:
        return output_after_soft_trim

    # --- Hard-clear pass -----------------------------------------------
    for i in prunable_tool_indexes:
        if ratio < settings.hard_clear_ratio:
            break
        current = (next_messages if next_messages is not None else messages)[i]
        if getattr(current, "role", None) != "toolResult":
            continue

        before_chars = _estimate_message_chars(current)
        placeholder_content = [_make_text_content(settings.hard_clear.placeholder)]
        cleared = _replace_content(current, placeholder_content)
        if next_messages is None:
            next_messages = list(messages)
        next_messages[i] = cleared
        after_chars = _estimate_message_chars(cleared)
        total_chars += after_chars - before_chars
        ratio = total_chars / char_window

    return next_messages if next_messages is not None else messages


# ---------------------------------------------------------------------------
# Index helpers
# ---------------------------------------------------------------------------


def _find_assistant_cutoff_index(
    messages: "list[AgentMessage]",
    keep_last_assistants: int,
) -> int | None:
    """Return index of the *keep_last_assistants*-th assistant from the end.

    Returns ``len(messages)`` when ``keep_last_assistants <= 0`` (everything
    is prunable).  Returns ``None`` if there are not enough assistant messages
    to establish a protected tail.

    Parity: ``findAssistantCutoffIndex``.
    """
    if keep_last_assistants <= 0:
        return len(messages)
    remaining = keep_last_assistants
    for i in range(len(messages) - 1, -1, -1):
        if getattr(messages[i], "role", None) == "assistant":
            remaining -= 1
            if remaining == 0:
                return i
    return None  # Not enough assistant messages.


def _find_first_user_index(messages: "list[AgentMessage]") -> int | None:
    """Parity: ``findFirstUserIndex``."""
    for i, msg in enumerate(messages):
        if getattr(msg, "role", None) == "user":
            return i
    return None


__all__ = [
    "CHARS_PER_TOKEN_ESTIMATE",
    "DEFAULT_CONTEXT_PRUNING_SETTINGS",
    "DEFAULT_PRUNABLE_TOOLS",
    "EffectiveContextPruningSettings",
    "HardClearSettings",
    "SoftTrimSettings",
    "prune_context_messages",
]
