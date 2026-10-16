"""jarvis.channels.inbound_context — prompt bodies and history context normalization.

OpenClaw parity: mirrors
``openclaw-main/src/auto-reply/reply/inbound-context.ts`` and
``openclaw-main/src/channels/inbound-event/context.ts``.

Populates prompt text fields:
- ``BodyForAgent``: Model-facing text for current turn (falls back to CommandBody / RawBody / Body).
- ``BodyForCommands``: Clean text for directive/command parsing (falls back to CommandBody / RawBody / Body).
- ``CommandBody``, ``RawBody``, ``Body``.
"""

from __future__ import annotations

import re
from typing import Any, TypedDict


class MsgContext(TypedDict, total=False):
    Body: str
    BodyForAgent: str
    BodyForCommands: str
    CommandBody: str
    RawBody: str
    Transcript: str
    ChatType: str
    Sender: str
    MessageId: str


def sanitize_inbound_system_tags(text: str | None) -> str:
    """Sanitize internal or injected system tags from inbound text."""
    if not text or not isinstance(text, str):
        return ""
    # Strip dangerous injected system tags
    sanitized = re.sub(r"<\s*/?\s*(?:system|context|instruction|relevant-memories)[^>]*>", "", text, flags=re.IGNORECASE)
    return sanitized


def normalize_inbound_text_newlines(text: str | None) -> str:
    """Normalize CRLF newlines to standard LF."""
    if not text or not isinstance(text, str):
        return ""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def resolve_body_for_agent(ctx: dict[str, Any]) -> str:
    """Resolve model-facing text for current turn with fallback cascade.

    Fallback order:
    1. ``BodyForAgent``
    2. ``CommandBody``
    3. ``RawBody``
    4. ``Body``
    """
    for key in ("BodyForAgent", "CommandBody", "RawBody", "Body"):
        val = ctx.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def resolve_body_for_commands(ctx: dict[str, Any]) -> str:
    """Resolve clean text used for directive/command parsing with fallback cascade.

    Fallback order:
    1. ``BodyForCommands``
    2. ``CommandBody``
    3. ``RawBody``
    4. ``Body``
    """
    for key in ("BodyForCommands", "CommandBody", "RawBody", "Body"):
        val = ctx.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def format_history_context_wrapper(history_lines: list[str], current_message: str) -> str:
    """Wrap channel history lines and current message body with standard envelopes.

    Mirrors OpenClaw's channel history wrapper format.
    """
    parts: list[str] = []
    if history_lines:
        parts.append("[Chat messages since your last reply - for context]")
        parts.extend(history_lines)
        parts.append("")

    parts.append("[Current message - respond to this]")
    parts.append(current_message)

    return "\n".join(parts)


def finalize_inbound_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Finalize and normalize inbound message context object.

    Mirrors ``finalizeInboundContext`` (``inbound-context.ts``).
    """
    res = dict(ctx)

    raw_body = res.get("Body")
    body_str = raw_body if isinstance(raw_body, str) else ""
    res["Body"] = sanitize_inbound_system_tags(normalize_inbound_text_newlines(body_str))

    res["BodyForAgent"] = resolve_body_for_agent(res)
    res["BodyForCommands"] = resolve_body_for_commands(res)

    return res


__all__ = [
    "finalize_inbound_context",
    "format_history_context_wrapper",
    "normalize_inbound_text_newlines",
    "resolve_body_for_agent",
    "resolve_body_for_commands",
    "sanitize_inbound_system_tags",
]
