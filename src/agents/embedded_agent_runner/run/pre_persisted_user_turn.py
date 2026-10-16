"""jarvis.agents.embedded_agent_runner.run.pre_persisted_user_turn — pre-persisted current-user-turn helpers.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/pre-persisted-user-turn.ts``.

Public surface:

Functions:

- :func:`session_messages_contain_idempotency_key`
- :func:`detach_pre_persisted_current_user_turn`

Phase 7.6g — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


#: Installable hook for the session-messages-contain-idempotency-key step.
_SESSION_MESSAGES_CONTAIN_IDEMPOTENCY_KEY: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_session_messages_contain_idempotency_key_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom sessionMessagesContainIdempotencyKey hook."""
    global _SESSION_MESSAGES_CONTAIN_IDEMPOTENCY_KEY
    _SESSION_MESSAGES_CONTAIN_IDEMPOTENCY_KEY = hook


#: Installable hook for the detach-pre-persisted-current-user-turn step.
_DETACH_PRE_PERSISTED_CURRENT_USER_TURN: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_detach_pre_persisted_current_user_turn_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom detachPrePersistedCurrentUserTurn hook."""
    global _DETACH_PRE_PERSISTED_CURRENT_USER_TURN
    _DETACH_PRE_PERSISTED_CURRENT_USER_TURN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def session_messages_contain_idempotency_key(
    params: Dict[str, Any],
) -> bool:
    """Return True when the session messages contain an idempotency key.

    Mirrors :func:`sessionMessagesContainIdempotencyKey`
    (``pre-persisted-user-turn.ts``).
    """
    return _SESSION_MESSAGES_CONTAIN_IDEMPOTENCY_KEY(dict(params or {}))


def detach_pre_persisted_current_user_turn(
    params: Dict[str, Any],
) -> Any:
    """Detach the pre-persisted current user turn.

    Mirrors :func:`detachPrePersistedCurrentUserTurn`
    (``pre-persisted-user-turn.ts``).
    """
    return _DETACH_PRE_PERSISTED_CURRENT_USER_TURN(dict(params or {}))


__all__ = [
    "detach_pre_persisted_current_user_turn",
    "session_messages_contain_idempotency_key",
    "set_detach_pre_persisted_current_user_turn_hook",
    "set_session_messages_contain_idempotency_key_hook",
]
