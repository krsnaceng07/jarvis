"""jarvis.agents.embedded_agent_runner.run.attempt_thread_helpers — thread-related helpers for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.thread-helpers.ts``.

Public surface:

Functions:

- :func:`compose_system_prompt_with_hook_context`
- :func:`resolve_attempt_spawn_workspace_dir`
- :func:`append_attempt_cache_ttl_if_needed`
- :func:`should_persist_completed_bootstrap_turn`

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Installable hook for the compose-system-prompt-with-hook-context step.
_COMPOSE_SYSTEM_PROMPT_WITH_HOOK_CONTEXT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_compose_system_prompt_with_hook_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom composeSystemPromptWithHookContext hook."""
    global _COMPOSE_SYSTEM_PROMPT_WITH_HOOK_CONTEXT
    _COMPOSE_SYSTEM_PROMPT_WITH_HOOK_CONTEXT = hook


#: Installable hook for the resolve-attempt-spawn-workspace-dir step.
_RESOLVE_ATTEMPT_SPAWN_WORKSPACE_DIR: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_attempt_spawn_workspace_dir_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveAttemptSpawnWorkspaceDir hook."""
    global _RESOLVE_ATTEMPT_SPAWN_WORKSPACE_DIR
    _RESOLVE_ATTEMPT_SPAWN_WORKSPACE_DIR = hook


#: Installable hook for the append-attempt-cache-ttl-if-needed step.
_APPEND_ATTEMPT_CACHE_TTL_IF_NEEDED: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_append_attempt_cache_ttl_if_needed_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom appendAttemptCacheTtlIfNeeded hook."""
    global _APPEND_ATTEMPT_CACHE_TTL_IF_NEEDED
    _APPEND_ATTEMPT_CACHE_TTL_IF_NEEDED = hook


#: Installable hook for the should-persist-completed-bootstrap-turn step.
_SHOULD_PERSIST_COMPLETED_BOOTSTRAP_TURN: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_persist_completed_bootstrap_turn_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldPersistCompletedBootstrapTurn hook."""
    global _SHOULD_PERSIST_COMPLETED_BOOTSTRAP_TURN
    _SHOULD_PERSIST_COMPLETED_BOOTSTRAP_TURN = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compose_system_prompt_with_hook_context(
    params: Dict[str, Any],
) -> Optional[str]:
    """Compose the system prompt with the hook context.

    Mirrors :func:`composeSystemPromptWithHookContext`
    (``attempt.thread-helpers.ts``).
    """
    return _COMPOSE_SYSTEM_PROMPT_WITH_HOOK_CONTEXT(dict(params or {}))


def resolve_attempt_spawn_workspace_dir(
    params: Dict[str, Any],
) -> Optional[str]:
    """Resolve the attempt spawn workspace dir.

    Mirrors :func:`resolveAttemptSpawnWorkspaceDir`
    (``attempt.thread-helpers.ts``).
    """
    return _RESOLVE_ATTEMPT_SPAWN_WORKSPACE_DIR(dict(params or {}))


def append_attempt_cache_ttl_if_needed(
    params: Dict[str, Any],
) -> Any:
    """Append the attempt cache TTL if needed.

    Mirrors :func:`appendAttemptCacheTtlIfNeeded`
    (``attempt.thread-helpers.ts``).
    """
    return _APPEND_ATTEMPT_CACHE_TTL_IF_NEEDED(dict(params or {}))


def should_persist_completed_bootstrap_turn(
    params: Dict[str, Any],
) -> bool:
    """Return True when the completed bootstrap turn should be persisted.

    Mirrors :func:`shouldPersistCompletedBootstrapTurn`
    (``attempt.thread-helpers.ts``).
    """
    return _SHOULD_PERSIST_COMPLETED_BOOTSTRAP_TURN(dict(params or {}))


__all__ = [
    "append_attempt_cache_ttl_if_needed",
    "compose_system_prompt_with_hook_context",
    "resolve_attempt_spawn_workspace_dir",
    "set_append_attempt_cache_ttl_if_needed_hook",
    "set_compose_system_prompt_with_hook_context_hook",
    "set_resolve_attempt_spawn_workspace_dir_hook",
    "set_should_persist_completed_bootstrap_turn_hook",
    "should_persist_completed_bootstrap_turn",
]
