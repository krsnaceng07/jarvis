"""jarvis.agents.embedded_agent_runner.replay_history — replay-history normalization.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/replay-history.ts``.

Public surface (mirrors the OpenClaw source):

- :func:`normalize_assistant_replay_content` — normalize the
  assistant content for a replay copy.
- :func:`sanitize_session_history` — sanitize the session history
  before replay.
- :func:`validate_replay_turns` — validate the replay turns after
  the history is sanitized.

Phase 7.5c — focused minimal port.

The OpenClaw source is 1000+ lines and tightly coupled to the
thinking-block repair, transcript-only detection, zero-usage
detection, bare-delivery-mirror detection, and message-content
reconciliation layers. The Python port keeps the public
surface but delegates the heavy detection / repair helpers to
installable hooks so the host can plug in the real layers as
they land.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: A single agent message (user / assistant / toolResult / etc.).
AgentMessage = Dict[str, Any]


#: Assistant replay message shape.
AssistantReplayMessage = Dict[str, Any]


#: The fallback text injected for empty assistant turns.
#: Mirrors :data:`STREAM_ERROR_FALLBACK_TEXT``
#: (``replay-history.ts:64``).
STREAM_ERROR_FALLBACK_TEXT: str = "[stream error: no content]"


# ============================================================================
# Installable helpers
# ============================================================================


#: Sanitize user replay content. The host installs the real
#: :func:`sanitizeUserReplayContent`` when the user-replay
#: content layer lands. The default returns the input unchanged.
_SANITIZE_USER_REPLAY_CONTENT: Callable[[Any], Any] = (
    lambda message: message
)


def set_sanitize_user_replay_content_hook(
    hook: Callable[[Any], Any],
) -> None:
    """Install a custom sanitize-user-replay-content hook."""
    global _SANITIZE_USER_REPLAY_CONTENT
    _SANITIZE_USER_REPLAY_CONTENT = hook


#: Check if a message is transcript-only OpenClaw assistant.
_IS_TRANSCRIPT_ONLY_OPENCLAW_ASSISTANT_MESSAGE: Callable[[Any], bool] = (
    lambda _message: False
)


def set_is_transcript_only_openclaw_assistant_message_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom is-transcript-only-openclaw-assistant hook."""
    global _IS_TRANSCRIPT_ONLY_OPENCLAW_ASSISTANT_MESSAGE
    _IS_TRANSCRIPT_ONLY_OPENCLAW_ASSISTANT_MESSAGE = hook


#: Normalize assistant text content. Returns a normalized
#: assistant message (or ``None`` to drop the message).
_NORMALIZE_ASSISTANT_REPLAY_TEXT_CONTENT: Callable[
    [Any, str], Optional[Dict[str, Any]]
] = (
    lambda message, _text: None
)


def set_normalize_assistant_replay_text_content_hook(
    hook: Callable[[Any, str], Optional[Dict[str, Any]]],
) -> None:
    """Install a custom normalize-assistant-replay-text-content hook."""
    global _NORMALIZE_ASSISTANT_REPLAY_TEXT_CONTENT
    _NORMALIZE_ASSISTANT_REPLAY_TEXT_CONTENT = hook


#: Normalize assistant block content. Returns a normalized
#: assistant message (or ``None`` to drop).
_NORMALIZE_ASSISTANT_REPLAY_BLOCK_CONTENT: Callable[
    [Any, List[Any]], Optional[Dict[str, Any]]
] = (
    lambda message, _content: message
)


def set_normalize_assistant_replay_block_content_hook(
    hook: Callable[[Any, List[Any]], Optional[Dict[str, Any]]],
) -> None:
    """Install a custom normalize-assistant-replay-block-content hook."""
    global _NORMALIZE_ASSISTANT_REPLAY_BLOCK_CONTENT
    _NORMALIZE_ASSISTANT_REPLAY_BLOCK_CONTENT = hook


#: Check if a message is a reasoning-only-length assistant turn.
_IS_REASONING_ONLY_LENGTH_ASSISTANT_TURN: Callable[[Any], bool] = (
    lambda _message: False
)


def set_is_reasoning_only_length_assistant_turn_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom is-reasoning-only-length hook."""
    global _IS_REASONING_ONLY_LENGTH_ASSISTANT_TURN
    _IS_REASONING_ONLY_LENGTH_ASSISTANT_TURN = hook


#: Check if a message is a zero-usage empty stop assistant turn.
_IS_ZERO_USAGE_EMPTY_STOP_ASSISTANT_TURN: Callable[[Any], bool] = (
    lambda _message: False
)


def set_is_zero_usage_empty_stop_assistant_turn_hook(
    hook: Callable[[Any], bool],
) -> None:
    """Install a custom is-zero-usage-empty-stop hook."""
    global _IS_ZERO_USAGE_EMPTY_STOP_ASSISTANT_TURN
    _IS_ZERO_USAGE_EMPTY_STOP_ASSISTANT_TURN = hook


#: Check if a message is a bare delivery mirror duplicate of the
#: previous message in the output list.
_IS_BARE_DELIVERY_MIRROR_DUPLICATE: Callable[
    [List[Any], Any], bool
] = (
    lambda _prev_list, _message: False
)


def set_is_bare_delivery_mirror_duplicate_hook(
    hook: Callable[[List[Any], Any], bool],
) -> None:
    """Install a custom is-bare-delivery-mirror-duplicate hook."""
    global _IS_BARE_DELIVERY_MIRROR_DUPLICATE
    _IS_BARE_DELIVERY_MIRROR_DUPLICATE = hook


#: Validate replay turns hook. The host installs the real
#: :func:`validateReplayTurns`` when the validation layer lands.
#: The default is a no-op that returns the messages unchanged.
_VALIDATE_REPLAY_TURNS: Callable[[Dict[str, Any]], Awaitable[List[Any]]] = (
    lambda params: _default_validate(params.get("messages") or [])
)


async def _default_validate(messages: List[Any]) -> List[Any]:
    return list(messages)


def set_validate_replay_turns_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[List[Any]]],
) -> None:
    """Install a custom validate-replay-turns hook."""
    global _VALIDATE_REPLAY_TURNS
    _VALIDATE_REPLAY_TURNS = hook


#: Sanitize-session-history hook. The host installs the real
#: :func:`sanitizeSessionHistory`` when the session-history
#: layer lands. The default is a no-op that returns the
#: messages unchanged.
_SANITIZE_SESSION_HISTORY: Callable[
    [Dict[str, Any]], Awaitable[List[Any]]
] = (
    lambda params: _default_sanitize(params.get("messages") or [])
)


async def _default_sanitize(messages: List[Any]) -> List[Any]:
    return list(messages)


def set_sanitize_session_history_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[List[Any]]],
) -> None:
    """Install a custom sanitize-session-history hook."""
    global _SANITIZE_SESSION_HISTORY
    _SANITIZE_SESSION_HISTORY = hook


# ============================================================================
# Public surface
# ============================================================================


def normalize_assistant_replay_content(
    messages: List[AgentMessage],
) -> List[AgentMessage]:
    """Normalize the assistant content for a replay copy.

    Mirrors :func:`normalizeAssistantReplayContent``
    (``replay-history.ts:291-...``).

    The Python port keeps the same control flow as the OpenClaw
    source and delegates the heavy detection / repair helpers
    to the installable hooks above.
    """
    touched = False
    out: List[AgentMessage] = []
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            sanitized = _SANITIZE_USER_REPLAY_CONTENT(message)
            if sanitized:
                out.append(sanitized)
            if sanitized is not message:
                touched = True
            continue
        if not (isinstance(message, dict) and message.get("role") == "assistant"):
            out.append(message)
            continue
        if _IS_TRANSCRIPT_ONLY_OPENCLAW_ASSISTANT_MESSAGE(message):
            touched = True
            continue
        assistant_message: AssistantReplayMessage = message
        replay_content = message.get("content")
        if isinstance(replay_content, str):
            normalized = _NORMALIZE_ASSISTANT_REPLAY_TEXT_CONTENT(
                message, replay_content
            )
            if normalized:
                out.append(normalized)
            touched = True
            continue
        if not isinstance(replay_content, list):
            replay_content = (
                [replay_content]
                if replay_content is not None
                and isinstance(replay_content, dict)
                else []
            )
            assistant_message = {**message, "content": replay_content}
            touched = True
        if isinstance(replay_content, list):
            normalized = _NORMALIZE_ASSISTANT_REPLAY_BLOCK_CONTENT(
                assistant_message, replay_content
            )
            if normalized is not assistant_message:
                touched = True
                if not normalized:
                    continue
                assistant_message = normalized
                replay_content = assistant_message.get("content")
        if _IS_REASONING_ONLY_LENGTH_ASSISTANT_TURN(assistant_message):
            touched = True
            continue
        if isinstance(replay_content, list) and len(replay_content) == 0:
            stop_reason = assistant_message.get("stopReason")
            if (
                stop_reason == "error"
                or _IS_ZERO_USAGE_EMPTY_STOP_ASSISTANT_TURN(assistant_message)
            ):
                out.append(
                    {
                        **assistant_message,
                        "content": [
                            {"type": "text", "text": STREAM_ERROR_FALLBACK_TEXT},
                        ],
                    }
                )
                touched = True
                continue
        if _IS_BARE_DELIVERY_MIRROR_DUPLICATE(out, assistant_message):
            touched = True
            continue
        out.append(assistant_message)
    return out if touched else list(messages)


async def sanitize_session_history(
    *,
    messages: List[AgentMessage],
    **kwargs: Any,
) -> List[AgentMessage]:
    """Sanitize the session history before replay.

    Mirrors :func:`sanitizeSessionHistory``
    (``replay-history.ts:731-...``).

    The Python port delegates to an installable hook; the
    default is a no-op pass-through.
    """
    return list(
        await _SANITIZE_SESSION_HISTORY(
            {"messages": messages, **kwargs}
        )
    )


async def validate_replay_turns(
    *,
    messages: List[AgentMessage],
    **kwargs: Any,
) -> List[AgentMessage]:
    """Validate the replay turns after sanitization.

    Mirrors :func:`validateReplayTurns``
    (``replay-history.ts:929-...``).

    The Python port delegates to an installable hook; the
    default is a no-op pass-through.
    """
    return list(
        await _VALIDATE_REPLAY_TURNS(
            {"messages": messages, **kwargs}
        )
    )


__all__ = [
    "AgentMessage",
    "AssistantReplayMessage",
    "STREAM_ERROR_FALLBACK_TEXT",
    "normalize_assistant_replay_content",
    "sanitize_session_history",
    "set_is_bare_delivery_mirror_duplicate_hook",
    "set_is_reasoning_only_length_assistant_turn_hook",
    "set_is_transcript_only_openclaw_assistant_message_hook",
    "set_is_zero_usage_empty_stop_assistant_turn_hook",
    "set_normalize_assistant_replay_block_content_hook",
    "set_normalize_assistant_replay_text_content_hook",
    "set_sanitize_session_history_hook",
    "set_sanitize_user_replay_content_hook",
    "set_validate_replay_turns_hook",
    "validate_replay_turns",
]
