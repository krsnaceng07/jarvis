"""jarvis.agents.embedded_agent_runner.thinking — sanitizes reasoning/thinking blocks for replay.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/thinking.ts``.

Public surface:

- :func:`strip_thinking_signatures_from_message`
- :func:`strip_stale_thinking_signatures_for_compaction_replay`
- :func:`strip_invalid_thinking_signatures`
- :func:`sanitize_thinking_for_replay`
- :func:`recover_anthropic_thinking`
- :func:`build_assistant_message_with_sanitized_thinking`
- :data:`THINKING_BLOCK_ERROR_PATTERN`
- :data:`OMITTED_ASSISTANT_REASONING_TEXT`

Phase 7.6h-5 — focused minimal port.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional


_log = logging.getLogger("jarvis.agents.embedded_agent_runner.thinking")


#: Pattern for thinking-block errors from providers.
THINKING_BLOCK_ERROR_PATTERN = re.compile(
    r"(?:thinking|redacted_thinking).*?(?:cannot be modified|signature|invalid|missing|empty|blank)"
    r"|"
    r"(?:signature|invalid|missing|empty|blank).*?(?:thinking|redacted_thinking)",
    re.IGNORECASE,
)

#: Neutral placeholder text used when thinking-only messages must stay replayable.
OMITTED_ASSISTANT_REASONING_TEXT = "[assistant reasoning omitted]"


# Installable hooks ---------------------------------------------------------

_strip_thinking_signatures_from_message_hook = None
_strip_stale_thinking_signatures_for_compaction_replay_hook = None
_strip_invalid_thinking_signatures_hook = None
_sanitize_thinking_for_replay_hook = None
_recover_anthropic_thinking_hook = None
_build_assistant_message_with_sanitized_thinking_hook = None


def set_strip_thinking_signatures_from_message_hook(fn) -> None:
    global _strip_thinking_signatures_from_message_hook
    _strip_thinking_signatures_from_message_hook = fn


def set_strip_stale_thinking_signatures_for_compaction_replay_hook(fn) -> None:
    global _strip_stale_thinking_signatures_for_compaction_replay_hook
    _strip_stale_thinking_signatures_for_compaction_replay_hook = fn


def set_strip_invalid_thinking_signatures_hook(fn) -> None:
    global _strip_invalid_thinking_signatures_hook
    _strip_invalid_thinking_signatures_hook = fn


def set_sanitize_thinking_for_replay_hook(fn) -> None:
    global _sanitize_thinking_for_replay_hook
    _sanitize_thinking_for_replay_hook = fn


def set_recover_anthropic_thinking_hook(fn) -> None:
    global _recover_anthropic_thinking_hook
    _recover_anthropic_thinking_hook = fn


def set_build_assistant_message_with_sanitized_thinking_hook(fn) -> None:
    global _build_assistant_message_with_sanitized_thinking_hook
    _build_assistant_message_with_sanitized_thinking_hook = fn


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _is_assistant_message_with_content(message: Any) -> bool:
    return (
        bool(message)
        and isinstance(message, dict)
        and message.get("role") == "assistant"
        and isinstance(message.get("content"), list)
    )


def _is_thinking_block(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    return block.get("type") in ("thinking", "redacted_thinking")


def _is_tool_call_block(block: Any) -> bool:
    if not isinstance(block, dict):
        return False
    return block.get("type") in ("toolCall", "tool_use", "function_call")


def _is_tool_result_message(message: Any) -> bool:
    return bool(message) and isinstance(message, dict) and message.get("role") == "toolResult"


def _is_signed_thinking_block(block: Dict[str, Any]) -> bool:
    if not _is_thinking_block(block):
        return False
    return (
        block.get("type") == "redacted_thinking"
        or block.get("signature") is not None
        or block.get("thinkingSignature") is not None
        or block.get("thought_signature") is not None
    )


def _has_meaningful_text(block: Any) -> bool:
    if not isinstance(block, dict) or block.get("type") != "text":
        return False
    text = block.get("text")
    return isinstance(text, str) and text.strip() != ""


def _build_omitted_assistant_reasoning_content() -> List[Dict[str, Any]]:
    return [{"type": "text", "text": OMITTED_ASSISTANT_REASONING_TEXT}]


def _parse_timestamp_ms(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value == value:
        return int(value)
    if isinstance(value, str):
        try:
            parsed = int(__import__("datetime").datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
            return parsed
        except Exception:
            try:
                f = float(value)
                if f == f:
                    return int(f)
            except Exception:
                return None
    return None


def _strip_signature_fields_from_thinking_block(block: Dict[str, Any]) -> Dict[str, Any]:
    record = dict(block)
    for key in ("thinkingSignature", "signature", "thought_signature"):
        record.pop(key, None)
    if record.get("type") == "redacted_thinking":
        record.pop("data", None)
    return record


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def strip_thinking_signatures_from_message(message: Any) -> Any:
    """Strip all thinking signature fields from a single assistant message.

    Mirrors :func:`stripThinkingSignaturesFromMessage` (``thinking.ts``).
    """
    if _strip_thinking_signatures_from_message_hook is not None:
        return _strip_thinking_signatures_from_message_hook(message)
    if not _is_assistant_message_with_content(message):
        return message
    new_content: List[Any] = []
    changed = False
    for block in message.get("content", []):
        if not _is_thinking_block(block):
            new_content.append(block)
            continue
        if not _is_signed_thinking_block(block):
            new_content.append(block)
            continue
        new_content.append(_strip_signature_fields_from_thinking_block(block))
        changed = True
    if not changed:
        return message
    return {**message, "content": new_content}


def strip_stale_thinking_signatures_for_compaction_replay(
    messages: List[Any],
) -> List[Any]:
    """Strip thinking signatures from pre-compaction assistant messages.

    Mirrors :func:`stripStaleThinkingSignaturesForCompactionReplay`
    (``thinking.ts``).
    """
    if _strip_stale_thinking_signatures_for_compaction_replay_hook is not None:
        return _strip_stale_thinking_signatures_for_compaction_replay_hook(messages) or messages
    if not isinstance(messages, list):
        return messages
    latest_compaction_ts: Optional[int] = None
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "compactionSummary":
            ts = _parse_timestamp_ms(m.get("timestamp"))
            if ts is not None:
                latest_compaction_ts = (
                    ts if latest_compaction_ts is None else max(latest_compaction_ts, ts)
                )
    if latest_compaction_ts is None:
        return messages
    out: List[Any] = []
    changed = False
    for m in messages:
        if not _is_assistant_message_with_content(m):
            out.append(m)
            continue
        ts = _parse_timestamp_ms(m.get("timestamp"))
        if ts is None or ts >= latest_compaction_ts:
            out.append(m)
            continue
        stripped = strip_thinking_signatures_from_message(m)
        if stripped is not m:
            changed = True
        out.append(stripped)
    return out if changed else messages


def strip_invalid_thinking_signatures(
    messages: List[Any],
    error_text: Optional[str] = None,
) -> List[Any]:
    """Strip thinking blocks that triggered a provider signature error.

    Mirrors :func:`stripInvalidThinkingSignatures` (``thinking.ts``).
    """
    if _strip_invalid_thinking_signatures_hook is not None:
        return _strip_invalid_thinking_signatures_hook({"messages": messages, "errorText": error_text}) or messages
    if not isinstance(messages, list):
        return messages
    if error_text and THINKING_BLOCK_ERROR_PATTERN.search(str(error_text)):
        return messages
    out: List[Any] = []
    changed = False
    for m in messages:
        if not _is_assistant_message_with_content(m):
            out.append(m)
            continue
        new_content: List[Any] = []
        block_changed = False
        for block in m.get("content", []):
            if _is_thinking_block(block):
                new_content.append(_strip_signature_fields_from_thinking_block(block))
                block_changed = True
            else:
                new_content.append(block)
        if block_changed:
            out.append({**m, "content": new_content})
            changed = True
        else:
            out.append(m)
    return out if changed else messages


def sanitize_thinking_for_replay(messages: List[Any]) -> List[Any]:
    """Strip thinking signatures from all assistant messages in a list.

    Mirrors :func:`sanitizeThinkingForReplay` (``thinking.ts``).
    """
    if _sanitize_thinking_for_replay_hook is not None:
        return _sanitize_thinking_for_replay_hook(messages) or messages
    if not isinstance(messages, list):
        return messages
    out: List[Any] = []
    changed = False
    for m in messages:
        if not _is_assistant_message_with_content(m):
            out.append(m)
            continue
        stripped = strip_thinking_signatures_from_message(m)
        if stripped is not m:
            changed = True
        out.append(stripped)
    return out if changed else messages


def recover_anthropic_thinking(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Recover an Anthropic thinking-block session after a signature failure.

    Mirrors :func:`recoverAnthropicThinking` (``thinking.ts``).
    """
    if _recover_anthropic_thinking_hook is not None:
        return _recover_anthropic_thinking_hook(params) or {}
    messages = params.get("messages")
    if not isinstance(messages, list):
        messages = []
    cleaned = sanitize_thinking_for_replay(messages)
    on_recovered = params.get("onRecoveredAnthropicThinking")
    if callable(on_recovered):
        try:
            res = on_recovered(
                {"originalMessages": messages, "cleanedMessages": cleaned}
            )
            if hasattr(res, "__await__"):
                # Best-effort; focused port does not block.
                pass
        except Exception:
            pass
    return {
        "originalMessages": messages,
        "cleanedMessages": cleaned,
    }


def build_assistant_message_with_sanitized_thinking(
    params: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a replayable assistant message with sanitized thinking blocks.

    Mirrors :func:`buildAssistantMessageWithSanitizedThinking` (``thinking.ts``).
    """
    if _build_assistant_message_with_sanitized_thinking_hook is not None:
        return _build_assistant_message_with_sanitized_thinking_hook(params) or {}
    message = params.get("message") or {}
    new_content: List[Any] = []
    dropped_thinking = False
    has_meaningful_text = False
    for block in message.get("content", []) if isinstance(message, dict) else []:
        if _is_thinking_block(block):
            stripped = _strip_signature_fields_from_thinking_block(block)
            if not _has_meaningful_text(stripped):
                dropped_thinking = True
                continue
            new_content.append(stripped)
            dropped_thinking = True
            continue
        new_content.append(block)
        if _has_meaningful_text(block):
            has_meaningful_text = True
    if dropped_thinking and not has_meaningful_text:
        new_content = _build_omitted_assistant_reasoning_content() + new_content
    return {
        **message,
        "content": new_content,
    }


__all__ = [
    "THINKING_BLOCK_ERROR_PATTERN",
    "OMITTED_ASSISTANT_REASONING_TEXT",
    "strip_thinking_signatures_from_message",
    "strip_stale_thinking_signatures_for_compaction_replay",
    "strip_invalid_thinking_signatures",
    "sanitize_thinking_for_replay",
    "recover_anthropic_thinking",
    "build_assistant_message_with_sanitized_thinking",
    "set_strip_thinking_signatures_from_message_hook",
    "set_strip_stale_thinking_signatures_for_compaction_replay_hook",
    "set_strip_invalid_thinking_signatures_hook",
    "set_sanitize_thinking_for_replay_hook",
    "set_recover_anthropic_thinking_hook",
    "set_build_assistant_message_with_sanitized_thinking_hook",
]
