"""jarvis.shared.chat_message_content — chat message text extractors.

OpenClaw parity: mirrors ``openclaw-main/src/shared/chat-message-content.ts``.
"""
from __future__ import annotations

import json
from typing import Any, Optional, TypedDict


AssistantPhase = str  # "commentary" | "final_answer"


def extract_first_text_block(message: Any) -> Optional[str]:
    """Return the inline string content or first array text block.

    Mirrors :func:`extractFirstTextBlock` (``shared/chat-message-content.ts``).
    """
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list) or not content:
        return None
    first = content[0]
    if not isinstance(first, dict):
        return None
    text = first.get("text")
    return text if isinstance(text, str) else None


def _is_assistant_text_content_block_type(value: Any) -> bool:
    return value in ("text", "input_text", "output_text")


def normalize_assistant_phase(value: Any) -> Optional[str]:
    """Return normalized assistant phase, or None for unknown.

    Mirrors :func:`normalizeAssistantPhase` (``shared/chat-message-content.ts``).
    """
    return value if value in ("commentary", "final_answer") else None


def parse_assistant_text_signature(value: Any) -> Optional[dict]:
    """Parse assistant text block signature, preserving legacy raw ids.

    Mirrors :func:`parseAssistantTextSignature`
    (``shared/chat-message-content.ts``).
    """
    if not isinstance(value, str) or not value.strip():
        return None
    if not value.startswith("{"):
        return {"id": value}
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or parsed.get("v") != 1:
        return None
    out: dict = {}
    if isinstance(parsed.get("id"), str):
        out["id"] = parsed["id"]
    phase = normalize_assistant_phase(parsed.get("phase"))
    if phase:
        out["phase"] = phase
    return out


def resolve_assistant_message_phase(message: Any) -> Optional[str]:
    """Return assistant phase only when top-level phase or all explicit blocks agree.

    Mirrors :func:`resolveAssistantMessagePhase`
    (``shared/chat-message-content.ts``).
    """
    if not isinstance(message, dict):
        return None
    direct = normalize_assistant_phase(message.get("phase"))
    if direct:
        return direct
    content = message.get("content")
    if not isinstance(content, list):
        return None
    explicit_phases: set = set()
    for block in content:
        if not isinstance(block, dict):
            continue
        if not _is_assistant_text_content_block_type(block.get("type")):
            continue
        sig = parse_assistant_text_signature(block.get("textSignature"))
        if sig and "phase" in sig:
            explicit_phases.add(sig["phase"])
    if len(explicit_phases) == 1:
        return next(iter(explicit_phases))
    return None


def resolve_assistant_event_phase(data: Any) -> Optional[str]:
    """Find assistant phase on event payloads that may wrap message-like records.

    Mirrors :func:`resolveAssistantEventPhase`
    (``shared/chat-message-content.ts``).
    """
    if not isinstance(data, dict):
        return None
    for key in ("phase", "message", "partial", "item"):
        v = data.get(key)
        if key == "phase":
            phase = normalize_assistant_phase(v)
            if phase:
                return phase
        else:
            phase = resolve_assistant_message_phase(v)
            if phase:
                return phase
    return resolve_assistant_message_phase(data)


def extract_assistant_text_for_phase(
    message: Any,
    *,
    phase: Optional[str] = None,
    sanitize_text=None,
    join_with: str = "\n",
) -> Optional[str]:
    """Extract assistant text for a phase without mixing legacy and phased text.

    Mirrors :func:`extractAssistantTextForPhase`
    (``shared/chat-message-content.ts``).
    """
    if not isinstance(message, dict):
        return None
    message_phase = normalize_assistant_phase(message.get("phase"))

    def _should_include(resolved):
        if phase:
            return resolved == phase
        return resolved is None

    def _sanitize(text):
        if sanitize_text:
            return sanitize_text(text)
        return text

    def _normalize_joined(text):
        t = text.strip()
        return t or None

    if isinstance(message.get("text"), str):
        if not _should_include(message_phase):
            return None
        return _normalize_joined(_sanitize(message["text"]))
    if isinstance(message.get("content"), str):
        if not _should_include(message_phase):
            return None
        return _normalize_joined(_sanitize(message["content"]))
    content = message.get("content")
    if not isinstance(content, list):
        return None

    has_explicit_phased = any(
        isinstance(b, dict)
        and _is_assistant_text_content_block_type(b.get("type"))
        and (parse_assistant_text_signature(b.get("textSignature")) or {}).get("phase")
        for b in content
    )
    if not phase and has_explicit_phased:
        return None

    parts: list = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if not _is_assistant_text_content_block_type(block.get("type")):
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        sig = parse_assistant_text_signature(block.get("textSignature"))
        resolved = (sig or {}).get("phase")
        if resolved is None and has_explicit_phased:
            resolved = None
        elif resolved is None and not has_explicit_phased:
            resolved = message_phase
        if not _should_include(resolved):
            continue
        sanitized = _sanitize(text)
        if sanitized.strip():
            parts.append(sanitized)
    if not parts:
        return None
    return _normalize_joined(join_with.join(parts))


def extract_assistant_visible_text(message: Any) -> Optional[str]:
    """Return user-visible assistant text, preferring final answers.

    Mirrors :func:`extractAssistantVisibleText`
    (``shared/chat-message-content.ts``).
    """
    final = extract_assistant_text_for_phase(message, phase="final_answer")
    if final:
        return final
    return extract_assistant_text_for_phase(message)


__all__ = [
    "AssistantPhase",
    "extract_first_text_block",
    "normalize_assistant_phase",
    "parse_assistant_text_signature",
    "resolve_assistant_message_phase",
    "resolve_assistant_event_phase",
    "extract_assistant_text_for_phase",
    "extract_assistant_visible_text",
]
