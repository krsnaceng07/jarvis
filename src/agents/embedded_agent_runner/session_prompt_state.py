"""jarvis.agents.embedded_agent_runner.session_prompt_state — process-local prompt projection state.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/session-prompt-state.ts``.

Public surface (mirrors the OpenClaw source):

- :data:`ToolResultPromptProjectionState` — TypedDict for the
  per-session tool-result projection state.
- :func:`clone_tool_result_prompt_projection_state` — deep-clone
  a projection state.
- :func:`get_embedded_session_prompt_state` — get the projection
  state for ``sessionId`` (LRU-bounded).
- :func:`clear_embedded_session_prompt_states` — drop the
  projection state for a list of session ids.
- :func:`mark_session_user_turns_sent` — record user-turn
  idempotency keys for sent turns.
- :func:`has_session_user_turn_been_sent` — check whether a
  user turn with the same idempotency key has been sent.

Phase 7.5a — focused minimal port.

The OpenClaw source uses
:func:`resolveGlobalSingleton` from
``shared/global-singleton.js``. The Python port uses a
process-local module-level dict with an LRU cap of
``MAX_SESSION_PROMPT_STATES=64``.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Set


#: Maximum number of session prompt states to retain.
#: Mirrors :data:`MAX_SESSION_PROMPT_STATES``
#: (``session-prompt-state.ts:17``).
MAX_SESSION_PROMPT_STATES: int = 64


#: Process-local LRU session prompt state map. Mirrors the
#: OpenClaw ``Map<string, EmbeddedSessionPromptState>``.
_SESSION_PROMPT_STATES: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_SESSION_PROMPT_STATES_LOCK = threading.Lock()


#: Tool-result prompt projection state shape. Mirrors
#: :class:`ToolResultPromptProjectionState``
#: (``session-prompt-state.ts:5-10``).
ToolResultPromptProjectionState = Dict[str, Any]


def _create_session_prompt_state() -> Dict[str, Any]:
    """Create a new empty session prompt state.

    Mirrors :func:`createSessionPromptState``
    (``session-prompt-state.ts:24-34``).
    """
    return {
        "toolResults": {
            "replacements": {},
            "frozen": set(),
            "ambiguousBaseKeys": set(),
            "sourceTextByKey": {},
        },
        "sentUserTurnIds": set(),
    }


def clone_tool_result_prompt_projection_state(
    state: ToolResultPromptProjectionState,
) -> ToolResultPromptProjectionState:
    """Deep-clone a projection state.

    Mirrors :func:`cloneToolResultPromptProjectionState``
    (``session-prompt-state.ts:36-45``).
    """
    return {
        "replacements": dict(state.get("replacements") or {}),
        "frozen": set(state.get("frozen") or set()),
        "ambiguousBaseKeys": set(state.get("ambiguousBaseKeys") or set()),
        "sourceTextByKey": {
            key: list(value)
            for key, value in (state.get("sourceTextByKey") or {}).items()
        },
    }


def get_embedded_session_prompt_state(
    session_id: str,
) -> Dict[str, Any]:
    """Get the projection state for ``session_id`` (LRU-bounded).

    Mirrors :func:`getEmbeddedSessionPromptState``
    (``session-prompt-state.ts:47-64``).
    """
    with _SESSION_PROMPT_STATES_LOCK:
        existing = _SESSION_PROMPT_STATES.get(session_id)
        if existing is not None:
            # LRU touch.
            _SESSION_PROMPT_STATES.move_to_end(session_id)
            return existing
        created = _create_session_prompt_state()
        _SESSION_PROMPT_STATES[session_id] = created
        while len(_SESSION_PROMPT_STATES) > MAX_SESSION_PROMPT_STATES:
            _SESSION_PROMPT_STATES.popitem(last=False)
        return created


def clear_embedded_session_prompt_states(
    session_ids: Iterable[Optional[str]],
) -> None:
    """Drop the projection state for a list of session ids.

    Mirrors :func:`clearEmbeddedSessionPromptStates``
    (``session-prompt-state.ts:66-73``).
    """
    with _SESSION_PROMPT_STATES_LOCK:
        for session_id in session_ids:
            normalized = session_id.strip() if isinstance(session_id, str) else None
            if normalized:
                _SESSION_PROMPT_STATES.pop(normalized, None)


def mark_session_user_turns_sent(
    state: Dict[str, Any],
    messages: List[Dict[str, Any]],
) -> None:
    """Record user-turn idempotency keys for sent turns.

    Mirrors :func:`markSessionUserTurnsSent``
    (``session-prompt-state.ts:75-88``).
    """
    sent: Set[str] = state.setdefault("sentUserTurnIds", set())
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") != "user":
            continue
        key = message.get("idempotencyKey")
        if isinstance(key, str) and key:
            sent.add(key)


def has_session_user_turn_been_sent(
    state: Dict[str, Any],
    message: Optional[Dict[str, Any]],
) -> Optional[bool]:
    """Check whether a user turn with the same idempotency key has been sent.

    Mirrors :func:`hasSessionUserTurnBeenSent``
    (``session-prompt-state.ts:90-101``).
    """
    if not message or not isinstance(message, dict):
        return None
    if message.get("role") != "user":
        return None
    key = message.get("idempotencyKey")
    if not isinstance(key, str) or not key:
        return None
    sent: Set[str] = state.get("sentUserTurnIds", set()) or set()
    return key in sent


__all__ = [
    "MAX_SESSION_PROMPT_STATES",
    "ToolResultPromptProjectionState",
    "clear_embedded_session_prompt_states",
    "clone_tool_result_prompt_projection_state",
    "get_embedded_session_prompt_state",
    "has_session_user_turn_been_sent",
    "mark_session_user_turns_sent",
]
