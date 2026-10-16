"""Compaction helper utilities: file-op tracking and conversation serialization.

Port of ``packages/agent-core/src/harness/compaction/utils.ts``.

``truncate_utf16_safe`` comes from ``jarvis_normalization_core`` (parity:
``@openclaw/normalization-core/utf16-slice``). The dev sandbox runs Python
3.10 where that package's ``__init__`` uses PEP 695 syntax and cannot be
imported, so a verbatim local fallback is kept for the shim environment;
the real (>=3.12) toolchain always uses the shared implementation.

Character counts here are UTF-16 code units — JavaScript ``string.length``
semantics — because the truncation marker reports "N more characters
truncated" and the tests pin the exact count across surrogate pairs.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .harness_types import FileOperations
from .truncate import code_unit_length

if TYPE_CHECKING:
    from jarvis_llm import Message

    from .types import AgentMessage

try:  # pragma: no cover - exercised only where the package imports
    from jarvis_normalization_core.text_utility import truncate_utf16_safe
except Exception:  # pragma: no cover - Python <3.12 sandbox fallback

    def truncate_utf16_safe(s: str, max_units: int) -> str:
        """Verbatim fallback of ``jarvis_normalization_core.text_utility``."""
        if max_units < 0:
            raise ValueError("max_units must be >= 0")
        if code_unit_length(s) <= max_units:
            return s
        out: list[str] = []
        used = 0
        for ch in s:
            cost = 2 if ord(ch) > 0xFFFF else 1
            if used + cost > max_units:
                break
            out.append(ch)
            used += cost
        return "".join(out)


def create_file_ops() -> FileOperations:
    """Create an empty file-operation accumulator. Parity: ``createFileOps``."""
    return FileOperations(read=set(), written=set(), edited=set())


def _block_get(block: Any, name: str) -> Any:
    """Read a field off a content block that may be a dataclass or a dict.

    TS sees plain objects either way; Python transcripts hold dataclasses
    while persisted/foreign blocks (e.g. Codex nested tool results) arrive
    as dicts. Both must serialize identically.
    """
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def extract_file_ops_from_message(message: "AgentMessage", file_ops: FileOperations) -> None:
    """Add file operations from assistant tool calls to an accumulator.

    Parity: ``extractFileOpsFromMessage``.
    """
    if getattr(message, "role", None) != "assistant":
        return
    content = getattr(message, "content", None)
    if not isinstance(content, list):
        return

    for block in content:
        if _block_get(block, "type") != "toolCall":
            continue
        args = _block_get(block, "arguments")
        name = _block_get(block, "name")
        if not isinstance(args, dict) or name is None:
            continue
        path = args.get("path")
        if not isinstance(path, str) or not path:
            continue
        if name == "read":
            file_ops.read.add(path)
        elif name == "write":
            file_ops.written.add(path)
        elif name == "edit":
            file_ops.edited.add(path)


def compute_file_lists(file_ops: FileOperations) -> tuple[list[str], list[str]]:
    """Compute sorted read-only and modified file lists.

    Parity: ``computeFileLists``. Returns ``(read_files, modified_files)``.
    """
    modified = set(file_ops.edited) | set(file_ops.written)
    read_files = sorted(f for f in file_ops.read if f not in modified)
    modified_files = sorted(modified)
    return read_files, modified_files


def format_file_operations(read_files: list[str], modified_files: list[str]) -> str:
    """Format file lists as summary metadata tags. Parity: ``formatFileOperations``."""
    sections: list[str] = []
    if read_files:
        sections.append("<read-files>\n" + "\n".join(read_files) + "\n</read-files>")
    if modified_files:
        sections.append("<modified-files>\n" + "\n".join(modified_files) + "\n</modified-files>")
    if not sections:
        return ""
    return "\n\n" + "\n\n".join(sections)


TOOL_RESULT_MAX_CHARS = 2000


def safe_json_stringify(value: Any) -> str:
    """Parity: the local ``safeJsonStringify``.

    ``JSON.stringify`` returning ``undefined`` (functions, symbols) maps to
    the unserializable branch here — Python's closest analogue is the
    ``TypeError`` ``json.dumps`` raises for those values.
    """
    try:
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return "[unserializable]"


def _truncate_for_summary(text: str, max_chars: int) -> str:
    """Parity: ``truncateForSummary``. Lengths are UTF-16 code units."""
    total = code_unit_length(text)
    if total <= max_chars:
        return text
    sliced = truncate_utf16_safe(text, max_chars)
    truncated_chars = total - code_unit_length(sliced)
    return f"{sliced}\n\n[... {truncated_chars} more characters truncated]"


def get_compaction_content_block_text(block: Any) -> str:
    """Extract text that compaction both estimates and includes in prompts.

    Parity: ``getCompactionContentBlockText``. Handles Codex-style nested
    tool-result blocks (``text`` beside ``content``) and snake-case
    ``tool_result`` types from foreign transcripts.
    """
    block_type = _block_get(block, "type")
    text = _block_get(block, "text")
    if block_type == "text" and text:
        return text
    if block_type not in ("toolResult", "tool_result"):
        return ""
    if text:
        return text
    content = _block_get(block, "content")
    return content if isinstance(content, str) else ""


def serialize_conversation(messages: "list[Message]") -> str:
    """Serialize LLM messages to plain text for summarization prompts.

    Parity: ``serializeConversation``.
    """
    parts: list[str] = []

    for msg in messages:
        role = getattr(msg, "role", None)
        if role == "user":
            raw = msg.content
            if isinstance(raw, str):
                content = raw
            else:
                content = "".join(
                    _block_get(c, "text")
                    for c in raw
                    if _block_get(c, "type") == "text" and _block_get(c, "text")
                )
            if content:
                parts.append(f"[User]: {content}")
        elif role == "assistant":
            text_parts: list[str] = []
            thinking_parts: list[str] = []
            tool_calls: list[str] = []

            for block in msg.content:
                block_type = _block_get(block, "type")
                if block_type == "text":
                    text_parts.append(_block_get(block, "text") or "")
                elif block_type == "thinking":
                    thinking_parts.append(_block_get(block, "thinking") or "")
                elif block_type == "toolCall":
                    args = _block_get(block, "arguments") or {}
                    args_str = ", ".join(f"{k}={safe_json_stringify(v)}" for k, v in args.items())
                    tool_calls.append(f"{_block_get(block, 'name')}({args_str})")

            if thinking_parts:
                parts.append("[Assistant thinking]: " + "\n".join(thinking_parts))
            if text_parts:
                parts.append("[Assistant]: " + "\n".join(text_parts))
            if tool_calls:
                parts.append("[Assistant tool calls]: " + "; ".join(tool_calls))
        elif role == "toolResult":
            content = "".join(get_compaction_content_block_text(block) for block in msg.content)
            if content:
                parts.append(
                    "[Tool result]: " + _truncate_for_summary(content, TOOL_RESULT_MAX_CHARS)
                )

    return "\n\n".join(parts)


__all__ = [
    "FileOperations",
    "TOOL_RESULT_MAX_CHARS",
    "compute_file_lists",
    "create_file_ops",
    "extract_file_ops_from_message",
    "format_file_operations",
    "get_compaction_content_block_text",
    "safe_json_stringify",
    "serialize_conversation",
    "truncate_utf16_safe",
]
