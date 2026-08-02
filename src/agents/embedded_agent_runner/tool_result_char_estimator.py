"""jarvis.agents.embedded_agent_runner.tool_result_char_estimator — message char estimation.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/tool-result-char-estimator.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`CHARS_PER_TOKEN_ESTIMATE` — chars per token estimate.
- :data:`TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE` — tool-result
  chars per token estimate (default ``2``).
- :data:`MessageCharEstimateCache` — WeakMap-based cache type.
- :func:`is_tool_result_message` — return True for tool-result
  messages.
- :func:`get_tool_result_text` — join the text chunks of a
  tool-result message.
- :func:`create_message_char_estimate_cache` — create a new
  WeakMap-backed cache.
- :func:`estimate_message_chars_cached` — return the cached
  estimate, computing and caching on miss.
- :func:`estimate_context_chars` — sum cached estimates for a
  list of messages.
- :func:`invalidate_message_chars_cache_entry` — drop a single
  cache entry.

Phase 7.4a — focused minimal port.

The OpenClaw source uses :func:`bashExecutionToText` and the
:data:`BRANCH_SUMMARY_PREFIX`/:data:`BRANCH_SUMMARY_SUFFIX`/
:data:`COMPACTION_SUMMARY_PREFIX`/:data:`COMPACTION_SUMMARY_SUFFIX`
constants from the runtime layer. The Python port delegates
those formatters to installable hooks so the host can plug in
the real runtime formatters when the runtime layer lands.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


#: Default chars-per-token estimate. Mirrors
#: :data:`CHARS_PER_TOKEN_ESTIMATE`` from ``utils/cjk-chars.js``.
CHARS_PER_TOKEN_ESTIMATE: int = 4

#: Tool-result chars per token estimate. Mirrors
#: :data:`TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE``
#: (``tool-result-char-estimator.ts:15``).
TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE: int = 2

#: Image char estimate (per image block).
IMAGE_CHAR_ESTIMATE: int = 8_000


#: Message-char-estimate cache (WeakMap). Mirrors
#: :class:`MessageCharEstimateCache``
#: (``tool-result-char-estimator.ts:18``).
MessageCharEstimateCache = "WeakMap"


#: Bash-execution-to-text formatter. The host installs the real
#: :func:`bashExecutionToText`` when the runtime layer lands.
#: The default returns ``""``.
_BASH_EXECUTION_TO_TEXT: Callable[[Any], str] = lambda _msg: ""

#: Branch-summary prefix + suffix. Defaults are empty so the
#: Python port produces a stable length without the runtime.
BRANCH_SUMMARY_PREFIX: str = ""
BRANCH_SUMMARY_SUFFIX: str = ""
COMPACTION_SUMMARY_PREFIX: str = ""
COMPACTION_SUMMARY_SUFFIX: str = ""


def set_bash_execution_to_text_hook(
    hook: Callable[[Any], str],
) -> None:
    """Install a custom bash-execution-to-text formatter hook."""
    global _BASH_EXECUTION_TO_TEXT
    _BASH_EXECUTION_TO_TEXT = hook


def set_branch_summary_markers(
    *,
    prefix: str = "",
    suffix: str = "",
) -> None:
    """Install branch-summary prefix + suffix markers."""
    global BRANCH_SUMMARY_PREFIX, BRANCH_SUMMARY_SUFFIX
    BRANCH_SUMMARY_PREFIX = prefix
    BRANCH_SUMMARY_SUFFIX = suffix


def set_compaction_summary_markers(
    *,
    prefix: str = "",
    suffix: str = "",
) -> None:
    """Install compaction-summary prefix + suffix markers."""
    global COMPACTION_SUMMARY_PREFIX, COMPACTION_SUMMARY_SUFFIX
    COMPACTION_SUMMARY_PREFIX = prefix
    COMPACTION_SUMMARY_SUFFIX = suffix


# Module-level WeakMap used for the cache. Tests can use
# :func:`create_message_char_estimate_cache` to create a fresh
# cache; the global cache lets the OpenClaw-style "process-local
# cache" semantics work in production.
_CACHES: List[Any] = []


def create_message_char_estimate_cache() -> Any:
    """Create a new WeakMap-backed char estimate cache.

    Mirrors :func:`createMessageCharEstimateCache``
    (``tool-result-char-estimator.ts:183-185``).
    """
    cache: Any = {}
    _CACHES.append(cache)
    return cache


def _is_text_block(block: Any) -> bool:
    if not block or not isinstance(block, dict):
        return False
    if block.get("type") != "text":
        return False
    return isinstance(block.get("text"), str)


def _is_image_block(block: Any) -> bool:
    if not block or not isinstance(block, dict):
        return False
    return block.get("type") == "image"


def _estimate_unknown_chars(value: Any) -> int:
    """Estimate chars for an unknown value.

    Mirrors :func:`estimateUnknownChars``
    (``tool-result-char-estimator.ts:35-48``).
    """
    if isinstance(value, str):
        return len(value)
    if value is None:
        return 0
    try:
        serialized = json.dumps(value)
        return len(serialized) if isinstance(serialized, str) else 0
    except (TypeError, ValueError):
        return 256


def is_tool_result_message(msg: Any) -> bool:
    """Return True if the message is a tool-result.

    Mirrors :func:`isToolResultMessage``
    (``tool-result-char-estimator.ts:50-54``).
    """
    if not msg or not isinstance(msg, dict):
        return False
    role = msg.get("role")
    type_ = msg.get("type")
    return role == "toolResult" or role == "tool" or type_ == "toolResult"


def _get_tool_result_content(msg: Any) -> List[Any]:
    """Return the content blocks of a tool-result message."""
    if not is_tool_result_message(msg):
        return []
    content = msg.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return content if isinstance(content, list) else []


def _estimate_content_block_chars(content: List[Any]) -> int:
    """Estimate chars for a list of content blocks.

    Mirrors :func:`estimateContentBlockChars``
    (``tool-result-char-estimator.ts:67-79``).
    """
    chars = 0
    for block in content:
        if _is_text_block(block):
            chars += len(block.get("text", ""))
        elif _is_image_block(block):
            chars += IMAGE_CHAR_ESTIMATE
        else:
            chars += _estimate_unknown_chars(block)
    return chars


def get_tool_result_text(msg: Any) -> str:
    """Join the text chunks of a tool-result message.

    Mirrors :func:`getToolResultText``
    (``tool-result-char-estimator.ts:81-90``).
    """
    content = _get_tool_result_content(msg)
    chunks: List[str] = []
    for block in content:
        if _is_text_block(block):
            chunks.append(block.get("text", ""))
    return "\n".join(chunks)


def _estimate_message_chars(msg: Any) -> int:
    """Estimate chars for one message.

    Mirrors :func:`estimateMessageChars``
    (``tool-result-char-estimator.ts:92-181``).
    """
    if not msg or not isinstance(msg, dict):
        return 0
    role = msg.get("role")
    if role == "user":
        content = msg.get("content")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            return _estimate_content_block_chars(content)
        return 0
    if role == "assistant":
        chars = 0
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if not block or not isinstance(block, dict):
                    continue
                type_ = block.get("type")
                if type_ == "text" and isinstance(block.get("text"), str):
                    chars += len(block["text"])
                elif type_ == "thinking" and isinstance(block.get("thinking"), str):
                    chars += len(block["thinking"])
                elif type_ == "toolCall":
                    try:
                        chars += len(json.dumps(block.get("arguments") or {}))
                    except (TypeError, ValueError):
                        chars += 128
                else:
                    chars += _estimate_unknown_chars(block)
        return chars
    if is_tool_result_message(msg):
        content = _get_tool_result_content(msg)
        chars = _estimate_content_block_chars(content)
        weighted = int(
            (chars * CHARS_PER_TOKEN_ESTIMATE) / TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE
        )
        # Always round up to the weighted count.
        weighted = (chars * CHARS_PER_TOKEN_ESTIMATE + TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE - 1) // TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE
        return max(chars, weighted)
    if role == "bashExecution":
        if msg.get("excludeFromContext") is True:
            return 0
        try:
            return len(_BASH_EXECUTION_TO_TEXT(msg))
        except Exception:
            return 0
    if role == "branchSummary":
        summary = msg.get("summary") if isinstance(msg.get("summary"), str) else ""
        return len(BRANCH_SUMMARY_PREFIX + summary + BRANCH_SUMMARY_SUFFIX)
    if role == "compactionSummary":
        summary = msg.get("summary") if isinstance(msg.get("summary"), str) else ""
        return len(COMPACTION_SUMMARY_PREFIX + summary + COMPACTION_SUMMARY_SUFFIX)
    if role == "custom":
        content = msg.get("content")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            return _estimate_content_block_chars(content)
        return 0
    return 256


def estimate_message_chars_cached(
    msg: Any,
    cache: Any,
) -> int:
    """Return the cached estimate, computing and caching on miss.

    Mirrors :func:`estimateMessageCharsCached``
    (``tool-result-char-estimator.ts:187-198``).
    """
    if not isinstance(cache, dict):
        return _estimate_message_chars(msg)
    hit = cache.get(id(msg))
    if hit is not None:
        return hit
    estimated = _estimate_message_chars(msg)
    cache[id(msg)] = estimated
    return estimated


def estimate_context_chars(
    messages: List[Any],
    cache: Any,
) -> int:
    """Sum cached estimates for a list of messages.

    Mirrors :func:`estimateContextChars``
    (``tool-result-char-estimator.ts:200-205``).
    """
    return sum(
        estimate_message_chars_cached(msg, cache) for msg in messages
    )


def invalidate_message_chars_cache_entry(
    cache: Any,
    msg: Any,
) -> None:
    """Drop a single cache entry.

    Mirrors :func:`invalidateMessageCharsCacheEntry``
    (``tool-result-char-estimator.ts:207-210``).
    """
    if not isinstance(cache, dict):
        return
    cache.pop(id(msg), None)


__all__ = [
    "BRANCH_SUMMARY_PREFIX",
    "BRANCH_SUMMARY_SUFFIX",
    "CHARS_PER_TOKEN_ESTIMATE",
    "COMPACTION_SUMMARY_PREFIX",
    "COMPACTION_SUMMARY_SUFFIX",
    "IMAGE_CHAR_ESTIMATE",
    "MessageCharEstimateCache",
    "TOOL_RESULT_CHARS_PER_TOKEN_ESTIMATE",
    "create_message_char_estimate_cache",
    "estimate_context_chars",
    "estimate_message_chars_cached",
    "get_tool_result_text",
    "invalidate_message_chars_cache_entry",
    "is_tool_result_message",
    "set_bash_execution_to_text_hook",
    "set_branch_summary_markers",
    "set_compaction_summary_markers",
]
