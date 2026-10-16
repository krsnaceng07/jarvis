"""jarvis.agents.tokens — silent-reply, heartbeat, and prompt token helpers.

OpenClaw parity: mirrors ``src/auto-reply/tokens.ts``.

Provides SILENT_REPLY_TOKEN ("NO_REPLY") detection, formatting artifact checks,
and silent text resolution per surface type.
"""

from __future__ import annotations

import json
import re

SILENT_REPLY_TOKEN: str = "NO_REPLY"
HEARTBEAT_TOKEN: str = "HEARTBEAT_OK"

_HARMONY_CHANNEL_MARKER_RE = re.compile(r"^\s*(?:set-thought\s+)?<[\w]*\|[^>]*>\s*$")
_BOX_DRAWING_HR_ONLY_RE = re.compile(r"^\s*─{3,}\s*$")


def is_internal_formatting_artifact(text: str | None) -> bool:
    """Return True if *text* is an internal formatting artifact."""
    if not text:
        return False
    return bool(_HARMONY_CHANNEL_MARKER_RE.match(text) or _BOX_DRAWING_HR_ONLY_RE.match(text))


def _strip_edge_punctuation(text: str) -> str:
    # Strip leading/trailing punctuation characters
    return re.sub(r"^[^\w\s]+|[^\w\s]+$", "", text, flags=re.UNICODE)


def is_silent_reply_text(
    text: str | None,
    token: str = SILENT_REPLY_TOKEN,
) -> bool:
    """Return True if *text* contains only token-only silent reply text.

    Mirrors ``isSilentReplyText`` (``auto-reply/tokens.ts``).
    """
    if not text or not isinstance(text, str):
        return False

    trimmed = text.strip()
    if not trimmed:
        return False

    # Check exact token or token repeated with spaces (case-insensitive)
    escaped_token = re.escape(token)
    exact_pattern = re.compile(rf"^\s*{escaped_token}(?:\s+{escaped_token})*\s*$", re.IGNORECASE)

    if exact_pattern.match(trimmed):
        return True

    # Strip edge punctuation and test again
    stripped = _strip_edge_punctuation(trimmed)
    if stripped and exact_pattern.match(stripped):
        return True

    # Check JSON string format: "NO_REPLY"
    if trimmed.startswith('"') and trimmed.endswith('"') and token.upper() in trimmed.upper():
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, str) and parsed.strip().upper() == token.upper():
                return True
        except Exception:
            pass

    # Check JSON object format: {"action": "NO_REPLY"}
    if trimmed.startswith("{") and trimmed.endswith("}") and token.upper() in trimmed.upper():
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, dict) and len(parsed) == 1 and "action" in parsed:
                act = parsed.get("action")
                if isinstance(act, str) and act.strip().upper() == token.upper():
                    return True
        except Exception:
            pass

    return False


def resolve_silent_reply_policy(
    conversation_type: str,
    text: str | None,
) -> str | None:
    """Resolve silent reply text for *conversation_type* ('direct', 'group', 'channel').

    Rules:
    - Direct conversations: NEVER deliver NO_REPLY text. Bare NO_REPLY is suppressed (returns None).
    - Groups/channels: Allow silence. Bare NO_REPLY is suppressed (returns None).
    - Substantive text: Delivered normally.
    """
    if not text:
        return None

    if is_silent_reply_text(text):
        return None

    return text


__all__ = [
    "HEARTBEAT_TOKEN",
    "SILENT_REPLY_TOKEN",
    "is_internal_formatting_artifact",
    "is_silent_reply_text",
    "resolve_silent_reply_policy",
]
