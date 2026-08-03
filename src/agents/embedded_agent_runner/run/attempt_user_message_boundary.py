"""jarvis.agents.embedded_agent_runner.run.attempt_user_message_boundary — user-message boundary helpers for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.user-message-boundary.ts``.

Public surface:

Types:

- :data:`UserTranscriptContext`
- :data:`CurrentUserTimestampMatch`

Functions:

- :func:`split_leading_timestamp_envelope`
- :func:`read_first_user_text`
- :func:`resolve_user_transcript_messages`
- :func:`project_persisted_sender_context`
- :func:`find_active_user_message_index`

Phase 7.6e — focused minimal port.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


#: User transcript context shape.
UserTranscriptContext = Dict[str, Any]


#: Current user timestamp match shape.
CurrentUserTimestampMatch = Dict[str, Any]


#: Pure helper regex for leading timestamp envelope.
_LEADING_TIMESTAMP_PATTERN: "re.Pattern[str]" = re.compile(
    r"^\s*\[([^\]]+)\]\s*"
)


#: Pure helper: split the leading timestamp envelope from a text.
def split_leading_timestamp_envelope(
    text: str,
) -> Dict[str, Optional[str]]:
    """Split a leading ``[timestamp]`` envelope from a text.

    Mirrors :func:`splitLeadingTimestampEnvelope`
    (``attempt.user-message-boundary.ts``).
    """
    if not isinstance(text, str) or not text:
        return {"timestamp": None, "body": text or ""}
    match = _LEADING_TIMESTAMP_PATTERN.match(text)
    if not match:
        return {"timestamp": None, "body": text}
    return {
        "timestamp": match.group(1).strip(),
        "body": text[match.end():],
    }


def read_first_user_text(content: Any) -> Optional[str]:
    """Read the first user-text fragment from a message content.

    Mirrors :func:`readFirstUserText`
    (``attempt.user-message-boundary.ts``).
    """
    if isinstance(content, str):
        return content or None
    if not isinstance(content, list):
        return None
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type") or block.get("kind")
        if kind not in ("text", None):
            continue
        text = block.get("text")
        if isinstance(text, str) and text:
            return text
    return None


#: Installable hook for the resolve-user-transcript-messages step.
_RESOLVE_USER_TRANSCRIPT_MESSAGES: Callable[
    [Dict[str, Any]], Any
] = lambda _p: []


def set_resolve_user_transcript_messages_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveUserTranscriptMessages hook."""
    global _RESOLVE_USER_TRANSCRIPT_MESSAGES
    _RESOLVE_USER_TRANSCRIPT_MESSAGES = hook


#: Installable hook for the project-persisted-sender-context step.
_PROJECT_PERSISTED_SENDER_CONTEXT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_project_persisted_sender_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom projectPersistedSenderContext hook."""
    global _PROJECT_PERSISTED_SENDER_CONTEXT
    _PROJECT_PERSISTED_SENDER_CONTEXT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def resolve_user_transcript_messages(
    params: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Resolve the user-transcript messages.

    Mirrors :func:`resolveUserTranscriptMessages`
    (``attempt.user-message-boundary.ts``).
    """
    result = _RESOLVE_USER_TRANSCRIPT_MESSAGES(dict(params or {}))
    return list(result or [])


def project_persisted_sender_context(
    params: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Project the persisted sender context.

    Mirrors :func:`projectPersistedSenderContext`
    (``attempt.user-message-boundary.ts``).
    """
    return _PROJECT_PERSISTED_SENDER_CONTEXT(dict(params or {}))


def find_active_user_message_index(messages: List[Any]) -> int:
    """Find the active user-message index.

    Mirrors :func:`findActiveUserMessageIndex`
    (``attempt.user-message-boundary.ts``).
    """
    if not isinstance(messages, list):
        return -1
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        return index
    return -1


__all__ = [
    "CurrentUserTimestampMatch",
    "UserTranscriptContext",
    "find_active_user_message_index",
    "project_persisted_sender_context",
    "read_first_user_text",
    "resolve_user_transcript_messages",
    "set_project_persisted_sender_context_hook",
    "set_resolve_user_transcript_messages_hook",
    "split_leading_timestamp_envelope",
]
