"""jarvis.agents.embedded_agent_runner.run.session_bootstrap — bootstrap the session-manager / engine for an embedded run.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/session-bootstrap.ts``.

Public surface:

Functions:

- :func:`build_context_engine_compaction_session_target`
- :func:`is_no_real_conversation_compaction_noop`
- :func:`reset_no_real_conversation_token_snapshot`

Phase 7.6h-2 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the build-context-engine-compaction-session-target step.
_BUILD_CONTEXT_ENGINE_COMPACTION_SESSION_TARGET: Callable[
    [Dict[str, Any]], Any
] = lambda _p: {}


def set_build_context_engine_compaction_session_target_session_bootstrap_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildContextEngineCompactionSessionTarget hook."""
    global _BUILD_CONTEXT_ENGINE_COMPACTION_SESSION_TARGET
    _BUILD_CONTEXT_ENGINE_COMPACTION_SESSION_TARGET = hook


#: Installable hook for the is-no-real-conversation-compaction-noop step.
_IS_NO_REAL_CONVERSATION_COMPACTION_NOOP: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_is_no_real_conversation_compaction_noop_session_bootstrap_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom isNoRealConversationCompactionNoop hook."""
    global _IS_NO_REAL_CONVERSATION_COMPACTION_NOOP
    _IS_NO_REAL_CONVERSATION_COMPACTION_NOOP = hook


#: Installable hook for the reset-no-real-conversation-token-snapshot step.
_RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT: Callable[
    [Dict[str, Any]], None
] = lambda _p: None


def set_reset_no_real_conversation_token_snapshot_session_bootstrap_hook(
    hook: Callable[[Dict[str, Any]], None],
) -> None:
    """Install a custom resetNoRealConversationTokenSnapshot hook."""
    global _RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT
    _RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_context_engine_compaction_session_target(
    params: Dict[str, Any],
) -> Any:
    """Build the context-engine compaction session target.

    Mirrors :func:`buildContextEngineCompactionSessionTarget`
    (``session-bootstrap.ts``).
    """
    return _BUILD_CONTEXT_ENGINE_COMPACTION_SESSION_TARGET(
        dict(params or {})
    )


def is_no_real_conversation_compaction_noop(
    params: Dict[str, Any],
) -> bool:
    """Return True when the compaction is a no-op (no real conversation).

    Mirrors :func:`isNoRealConversationCompactionNoop`
    (``session-bootstrap.ts``).
    """
    return _IS_NO_REAL_CONVERSATION_COMPACTION_NOOP(dict(params or {}))


def reset_no_real_conversation_token_snapshot(
    params: Dict[str, Any],
) -> None:
    """Reset the no-real-conversation token snapshot.

    Mirrors :func:`resetNoRealConversationTokenSnapshot`
    (``session-bootstrap.ts``).
    """
    _RESET_NO_REAL_CONVERSATION_TOKEN_SNAPSHOT(dict(params or {}))


__all__ = [
    "build_context_engine_compaction_session_target",
    "is_no_real_conversation_compaction_noop",
    "reset_no_real_conversation_token_snapshot",
    "set_build_context_engine_compaction_session_target_session_bootstrap_hook",
    "set_is_no_real_conversation_compaction_noop_session_bootstrap_hook",
    "set_reset_no_real_conversation_token_snapshot_session_bootstrap_hook",
]
