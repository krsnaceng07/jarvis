"""jarvis.agents.embedded_agent_runner.run.attempt_prompt_helpers — prompt-build helpers for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.prompt-helpers.ts``.

Public surface:

Functions:

- :func:`forget_prompt_build_drain_cache_for_run`
- :func:`resolve_prompt_build_hook_result` (async)
- :func:`resolve_prompt_mode_for_session`
- :func:`should_inject_heartbeat_prompt`
- :func:`should_warn_on_orphaned_user_repair`
- :func:`merge_orphaned_trailing_user_prompt`
- :func:`resolve_attempt_fs_workspace_only`
- :func:`prepend_system_prompt_addition`
- :func:`resolve_attempt_media_task_system_prompt_addition`
- :func:`build_after_turn_runtime_context`
- :func:`build_after_turn_runtime_context_from_usage`

Phase 7.6f-2 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Optional


#: Prompt mode type alias.
PromptMode = str  # "minimal" | "full"


#: Installable hook for the forget-prompt-build-drain-cache-for-run step.
_FORGET_PROMPT_BUILD_DRAIN_CACHE_FOR_RUN: Callable[
    [Optional[str]], None
] = lambda _r: None


def set_forget_prompt_build_drain_cache_for_run_hook(
    hook: Callable[[Optional[str]], None],
) -> None:
    """Install a custom forgetPromptBuildDrainCacheForRun hook."""
    global _FORGET_PROMPT_BUILD_DRAIN_CACHE_FOR_RUN
    _FORGET_PROMPT_BUILD_DRAIN_CACHE_FOR_RUN = hook


#: Installable hook for the resolve-prompt-build-hook-result step.
_RESOLVE_PROMPT_BUILD_HOOK_RESULT: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_resolve_prompt_build_hook_result_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom resolvePromptBuildHookResult hook."""
    global _RESOLVE_PROMPT_BUILD_HOOK_RESULT
    _RESOLVE_PROMPT_BUILD_HOOK_RESULT = hook


#: Installable hook for the resolve-prompt-mode-for-session step.
_RESOLVE_PROMPT_MODE_FOR_SESSION: Callable[
    [Optional[str]], PromptMode
] = lambda _sk: "full"


def set_resolve_prompt_mode_for_session_hook(
    hook: Callable[[Optional[str]], PromptMode],
) -> None:
    """Install a custom resolvePromptModeForSession hook."""
    global _RESOLVE_PROMPT_MODE_FOR_SESSION
    _RESOLVE_PROMPT_MODE_FOR_SESSION = hook


#: Installable hook for the should-inject-heartbeat-prompt step.
_SHOULD_INJECT_HEARTBEAT_PROMPT: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_inject_heartbeat_prompt_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldInjectHeartbeatPrompt hook."""
    global _SHOULD_INJECT_HEARTBEAT_PROMPT
    _SHOULD_INJECT_HEARTBEAT_PROMPT = hook


#: Installable hook for the should-warn-on-orphaned-user-repair step.
_SHOULD_WARN_ON_ORPHANED_USER_REPAIR: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_warn_on_orphaned_user_repair_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldWarnOnOrphanedUserRepair hook."""
    global _SHOULD_WARN_ON_ORPHANED_USER_REPAIR
    _SHOULD_WARN_ON_ORPHANED_USER_REPAIR = hook


#: Installable hook for the merge-orphaned-trailing-user-prompt step.
_MERGE_ORPHANED_TRAILING_USER_PROMPT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_merge_orphaned_trailing_user_prompt_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom mergeOrphanedTrailingUserPrompt hook."""
    global _MERGE_ORPHANED_TRAILING_USER_PROMPT
    _MERGE_ORPHANED_TRAILING_USER_PROMPT = hook


#: Installable hook for the resolve-attempt-fs-workspace-only step.
_RESOLVE_ATTEMPT_FS_WORKSPACE_ONLY: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_resolve_attempt_fs_workspace_only_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom resolveAttemptFsWorkspaceOnly hook."""
    global _RESOLVE_ATTEMPT_FS_WORKSPACE_ONLY
    _RESOLVE_ATTEMPT_FS_WORKSPACE_ONLY = hook


#: Installable hook for the prepend-system-prompt-addition step.
_PREPEND_SYSTEM_PROMPT_ADDITION: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_prepend_system_prompt_addition_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom prependSystemPromptAddition hook."""
    global _PREPEND_SYSTEM_PROMPT_ADDITION
    _PREPEND_SYSTEM_PROMPT_ADDITION = hook


#: Installable hook for the resolve-attempt-media-task-system-prompt-addition step.
_RESOLVE_ATTEMPT_MEDIA_TASK_SYSTEM_PROMPT_ADDITION: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_resolve_attempt_media_task_system_prompt_addition_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom resolveAttemptMediaTaskSystemPromptAddition hook."""
    global _RESOLVE_ATTEMPT_MEDIA_TASK_SYSTEM_PROMPT_ADDITION
    _RESOLVE_ATTEMPT_MEDIA_TASK_SYSTEM_PROMPT_ADDITION = hook


#: Installable hook for the build-after-turn-runtime-context step.
_BUILD_AFTER_TURN_RUNTIME_CONTEXT: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_build_after_turn_runtime_context_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildAfterTurnRuntimeContext hook."""
    global _BUILD_AFTER_TURN_RUNTIME_CONTEXT
    _BUILD_AFTER_TURN_RUNTIME_CONTEXT = hook


#: Installable hook for the build-after-turn-runtime-context-from-usage step.
_BUILD_AFTER_TURN_RUNTIME_CONTEXT_FROM_USAGE: Callable[
    [Dict[str, Any]], Any
] = lambda _p: None


def set_build_after_turn_runtime_context_from_usage_hook(
    hook: Callable[[Dict[str, Any]], Any],
) -> None:
    """Install a custom buildAfterTurnRuntimeContextFromUsage hook."""
    global _BUILD_AFTER_TURN_RUNTIME_CONTEXT_FROM_USAGE
    _BUILD_AFTER_TURN_RUNTIME_CONTEXT_FROM_USAGE = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def forget_prompt_build_drain_cache_for_run(run_id: Optional[str]) -> None:
    """Forget the prompt-build drain cache for a run.

    Mirrors :func:`forgetPromptBuildDrainCacheForRun`
    (``attempt.prompt-helpers.ts``).
    """
    _FORGET_PROMPT_BUILD_DRAIN_CACHE_FOR_RUN(run_id)


async def resolve_prompt_build_hook_result(
    params: Dict[str, Any],
) -> Any:
    """Resolve the prompt-build hook result.

    Mirrors :func:`resolvePromptBuildHookResult`
    (``attempt.prompt-helpers.ts``).
    """
    return await _maybe_await(
        _RESOLVE_PROMPT_BUILD_HOOK_RESULT(dict(params or {}))
    )


def resolve_prompt_mode_for_session(
    session_key: Optional[str] = None,
) -> PromptMode:
    """Resolve the prompt mode for a session.

    Mirrors :func:`resolvePromptModeForSession`
    (``attempt.prompt-helpers.ts``).
    """
    return _RESOLVE_PROMPT_MODE_FOR_SESSION(session_key)


def should_inject_heartbeat_prompt(params: Dict[str, Any]) -> bool:
    """Return True when a heartbeat prompt should be injected.

    Mirrors :func:`shouldInjectHeartbeatPrompt`
    (``attempt.prompt-helpers.ts``).
    """
    return _SHOULD_INJECT_HEARTBEAT_PROMPT(dict(params or {}))


def should_warn_on_orphaned_user_repair(params: Dict[str, Any]) -> bool:
    """Return True when an orphaned-user-repair warning should fire.

    Mirrors :func:`shouldWarnOnOrphanedUserRepair`
    (``attempt.prompt-helpers.ts``).
    """
    return _SHOULD_WARN_ON_ORPHANED_USER_REPAIR(dict(params or {}))


def merge_orphaned_trailing_user_prompt(
    params: Dict[str, Any],
) -> Any:
    """Merge an orphaned trailing user prompt.

    Mirrors :func:`mergeOrphanedTrailingUserPrompt`
    (``attempt.prompt-helpers.ts``).
    """
    return _MERGE_ORPHANED_TRAILING_USER_PROMPT(dict(params or {}))


def resolve_attempt_fs_workspace_only(
    params: Dict[str, Any],
) -> bool:
    """Return True when the attempt is fs-workspace-only.

    Mirrors :func:`resolveAttemptFsWorkspaceOnly`
    (``attempt.prompt-helpers.ts``).
    """
    return _RESOLVE_ATTEMPT_FS_WORKSPACE_ONLY(dict(params or {}))


def prepend_system_prompt_addition(
    params: Dict[str, Any],
) -> Any:
    """Prepend a system-prompt addition.

    Mirrors :func:`prependSystemPromptAddition`
    (``attempt.prompt-helpers.ts``).
    """
    return _PREPEND_SYSTEM_PROMPT_ADDITION(dict(params or {}))


def resolve_attempt_media_task_system_prompt_addition(
    params: Dict[str, Any],
) -> Any:
    """Resolve the attempt media-task system-prompt addition.

    Mirrors :func:`resolveAttemptMediaTaskSystemPromptAddition`
    (``attempt.prompt-helpers.ts``).
    """
    return _RESOLVE_ATTEMPT_MEDIA_TASK_SYSTEM_PROMPT_ADDITION(
        dict(params or {})
    )


def build_after_turn_runtime_context(
    params: Dict[str, Any],
) -> Any:
    """Build the after-turn runtime context.

    Mirrors :func:`buildAfterTurnRuntimeContext`
    (``attempt.prompt-helpers.ts``).
    """
    return _BUILD_AFTER_TURN_RUNTIME_CONTEXT(dict(params or {}))


def build_after_turn_runtime_context_from_usage(
    params: Dict[str, Any],
) -> Any:
    """Build the after-turn runtime context from usage.

    Mirrors :func:`buildAfterTurnRuntimeContextFromUsage`
    (``attempt.prompt-helpers.ts``).
    """
    return _BUILD_AFTER_TURN_RUNTIME_CONTEXT_FROM_USAGE(
        dict(params or {})
    )


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "PromptMode",
    "build_after_turn_runtime_context",
    "build_after_turn_runtime_context_from_usage",
    "forget_prompt_build_drain_cache_for_run",
    "merge_orphaned_trailing_user_prompt",
    "prepend_system_prompt_addition",
    "resolve_attempt_fs_workspace_only",
    "resolve_attempt_media_task_system_prompt_addition",
    "resolve_prompt_build_hook_result",
    "resolve_prompt_mode_for_session",
    "set_build_after_turn_runtime_context_from_usage_hook",
    "set_build_after_turn_runtime_context_hook",
    "set_forget_prompt_build_drain_cache_for_run_hook",
    "set_merge_orphaned_trailing_user_prompt_hook",
    "set_prepend_system_prompt_addition_hook",
    "set_resolve_attempt_fs_workspace_only_hook",
    "set_resolve_attempt_media_task_system_prompt_addition_hook",
    "set_resolve_prompt_build_hook_result_hook",
    "set_resolve_prompt_mode_for_session_hook",
    "set_should_inject_heartbeat_prompt_hook",
    "set_should_warn_on_orphaned_user_repair_hook",
    "should_inject_heartbeat_prompt",
    "should_warn_on_orphaned_user_repair",
]
