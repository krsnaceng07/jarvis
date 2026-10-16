"""Assistant-message promotion for standalone plain-text tool calls.

OpenClaw parity: ``packages/tool-call-repair/src/promote.ts``.
Rewrites standalone assistant text as provider-neutral ``toolCall``
content blocks when (and only when) every block resolves against the
allowed tool set. Anything unresolvable — unknown names, protected
ranges, non-text content — declines with ``None`` instead of
publishing a partial rewrite.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from jarvis_normalization_core.string_coerce import as_optional_record

from .contracts import PlainTextToolCallProtectedRangeResolver
from .grammar import StructuralLineBreaks
from .payload import PlainTextToolCallBlock, parse_standalone_plain_text_tool_call_blocks

#: Resolves model-emitted tool names to exact request-allowed names.
ToolCallRepairNameResolver = Callable[[str, frozenset[str]], str | None]

#: Builds a provider-native tool-call block from a repaired payload.
PromotedBlockFactory = Callable[[PlainTextToolCallBlock, str], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PromotionOptions:
    """Controls when standalone assistant text may become tool-call content."""

    allowed_tool_names: frozenset[str] = frozenset()
    create_tool_call_block: PromotedBlockFactory | None = None
    message: Any = None
    allowed_stop_reasons: frozenset[Any] | None = None
    require_assistant_role: bool = False
    resolve_protected_ranges: PlainTextToolCallProtectedRangeResolver | None = None
    resolve_tool_name: ToolCallRepairNameResolver | None = None
    is_retainable_non_text_block: Callable[[dict[str, Any]], bool] | None = None


@dataclass(frozen=True, slots=True)
class MessageProjection:
    """Projected message plus source→projected content index mapping."""

    message: dict[str, Any] = field(default_factory=dict)
    source_to_projected_content_index: dict[int, int] = field(default_factory=dict)


def create_promoted_plain_text_tool_call_block(
    block: PlainTextToolCallBlock, name: str
) -> dict[str, Any]:
    """Build the shared assistant-message shape for a repaired text tool call."""
    identity = hashlib.sha256(
        f"{block.start}:{block.end}:{name}:{block.raw}".encode("utf-8")
    ).hexdigest()[:24]
    return {
        "type": "toolCall",
        "id": f"call_{identity}",
        "name": name,
        "arguments": block.arguments,
        "partialArgs": json.dumps(block.arguments),
    }


def create_promoted_plain_text_tool_call_events(
    message: dict[str, Any],
) -> list[dict[str, Any]]:
    """Emit the complete provider-neutral lifecycle for promoted blocks."""
    content = message.get("content")
    blocks: list[Any] = content if isinstance(content, list) else []
    events: list[dict[str, Any]] = []
    for content_index, block in enumerate(blocks):
        tool_call = as_optional_record(block)
        if tool_call is None or tool_call.get("type") != "toolCall":
            continue
        partial_args = tool_call.get("partialArgs")
        events.append({"type": "toolcall_start", "contentIndex": content_index, "partial": message})
        events.append(
            {
                "type": "toolcall_delta",
                "contentIndex": content_index,
                "delta": partial_args if isinstance(partial_args, str) else "{}",
                "partial": message,
            }
        )
        events.append(
            {
                "type": "toolcall_end",
                "contentIndex": content_index,
                "toolCall": tool_call,
                "partial": message,
            }
        )
    return events


def _resolve_exact_tool_name(raw_name: str, allowed: frozenset[str]) -> str | None:
    return raw_name if raw_name in allowed else None


def _promoted_blocks_from_text(
    text: str,
    options: PromotionOptions,
    line_break_offsets: frozenset[int] | None = None,
) -> list[dict[str, Any]] | None:
    parsed = parse_standalone_plain_text_tool_call_blocks(
        text,
        None,
        StructuralLineBreaks(line_break_offsets=line_break_offsets or frozenset()),
    )
    if parsed is None:
        return None
    protected = (
        options.resolve_protected_ranges(text)
        if options.resolve_protected_ranges is not None
        else []
    )
    if any(
        block.start >= item.start and block.start < item.end
        for block in parsed
        for item in protected
    ):
        return None
    resolve_tool_name = options.resolve_tool_name or _resolve_exact_tool_name
    create_block = options.create_tool_call_block
    if create_block is None:
        return None
    tool_calls: list[dict[str, Any]] = []
    for block in parsed:
        resolved = resolve_tool_name(block.name, options.allowed_tool_names)
        if not resolved:
            return None
        tool_calls.append(create_block(block, resolved))
    return tool_calls


def _promoted_blocks_from_text_parts(
    text_parts: list[str], options: PromotionOptions
) -> list[dict[str, Any]] | None:
    text = "".join(text_parts)
    if not text.strip():
        return []
    offset = 0
    line_break_offsets: set[int] = set()
    for part in text_parts[:-1]:
        offset += len(part)
        line_break_offsets.add(offset)
    line_break_offsets.discard(len(text))
    return _promoted_blocks_from_text(text, options, frozenset(line_break_offsets))


def project_standalone_plain_text_tool_call_message(
    options: PromotionOptions,
) -> MessageProjection | None:
    """Promote text calls and map source blocks retained in the projection."""
    message = as_optional_record(options.message)
    if (
        message is None
        or not options.allowed_tool_names
        or (options.require_assistant_role and message.get("role") != "assistant")
        or (
            options.allowed_stop_reasons is not None
            and message.get("stopReason") not in options.allowed_stop_reasons
        )
    ):
        return None

    original_content = message.get("content")
    if isinstance(original_content, str):
        tool_calls = _promoted_blocks_from_text(original_content, options)
        if tool_calls is None:
            return None
        return MessageProjection(
            message={**message, "content": tool_calls, "stopReason": "toolUse"},
            source_to_projected_content_index={},
        )

    if not isinstance(original_content, list):
        return None
    items: list[Any] = original_content

    content: list[dict[str, Any]] = []
    index_map: dict[int, int] = {}
    promoted_text_block = False
    text_parts: list[str] = []

    def flush_text_parts() -> bool:
        nonlocal promoted_text_block
        tool_calls = _promoted_blocks_from_text_parts(text_parts, options)
        text_parts.clear()
        if tool_calls is None:
            return False
        content.extend(tool_calls)
        promoted_text_block = promoted_text_block or len(tool_calls) > 0
        return True

    for source_index, block in enumerate(items):
        block_record = as_optional_record(block)
        if block_record is None:
            return None
        if block_record.get("type") == "text":
            if not isinstance(block_record.get("text"), str):
                return None
            text_value: str = block_record["text"]
            text_parts.append(text_value)
            continue
        if not flush_text_parts():
            return None
        retain = options.is_retainable_non_text_block
        if retain is not None and retain(block_record):
            index_map[source_index] = len(content)
            content.append(block_record)
            continue
        return None

    if not flush_text_parts():
        return None
    if not promoted_text_block:
        return None
    return MessageProjection(
        message={**message, "content": content, "stopReason": "toolUse"},
        source_to_projected_content_index=index_map,
    )


__all__ = [
    "MessageProjection",
    "PromotedBlockFactory",
    "PromotionOptions",
    "ToolCallRepairNameResolver",
    "create_promoted_plain_text_tool_call_block",
    "create_promoted_plain_text_tool_call_events",
    "project_standalone_plain_text_tool_call_message",
]
