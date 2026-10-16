"""jarvis.agents.embedded_agent_runner.run.attempt_async_tasks — wait for completion-required async tasks for an attempt.

OpenClaw parity: mirrors
``openclaw-main/src/agents/embedded-agent-runner/run/attempt.async-tasks.ts``.

Public surface:

Types:

- :data:`AsyncStartedToolMeta`
- :data:`CompletionRequiredAsyncTaskWaitResult`

Functions:

- :func:`requires_completion_required_async_task_wait`
- :func:`should_wait_for_completion_required_async_tasks`
- :func:`wait_for_completion_required_async_tasks` (async)

Phase 7.6d-7 — focused minimal port.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict


#: Async-started tool meta shape.
AsyncStartedToolMeta = Dict[str, Any]


#: Completion-required async-task wait result.
CompletionRequiredAsyncTaskWaitResult = Dict[str, Any]


#: Installable hook for the requires-completion-required-async-task-wait step.
_REQUIRES_COMPLETION_REQUIRED_ASYNC_TASK_WAIT: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_requires_completion_required_async_task_wait_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom requiresCompletionRequiredAsyncTaskWait hook."""
    global _REQUIRES_COMPLETION_REQUIRED_ASYNC_TASK_WAIT
    _REQUIRES_COMPLETION_REQUIRED_ASYNC_TASK_WAIT = hook


#: Installable hook for the should-wait-for-completion-required-async-tasks step.
_SHOULD_WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS: Callable[
    [Dict[str, Any]], bool
] = lambda _p: False


def set_should_wait_for_completion_required_async_tasks_hook(
    hook: Callable[[Dict[str, Any]], bool],
) -> None:
    """Install a custom shouldWaitForCompletionRequiredAsyncTasks hook."""
    global _SHOULD_WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS
    _SHOULD_WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS = hook


#: Installable hook for the wait-for-completion-required-async-tasks step.
_WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS: Callable[
    [Dict[str, Any]], Awaitable[Any]
] = lambda _p: asyncio.sleep(0)


def set_wait_for_completion_required_async_tasks_hook(
    hook: Callable[[Dict[str, Any]], Awaitable[Any]],
) -> None:
    """Install a custom waitForCompletionRequiredAsyncTasks hook."""
    global _WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS
    _WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS = hook


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def requires_completion_required_async_task_wait(
    params: Dict[str, Any],
) -> bool:
    """Return True when the attempt needs to wait for async tasks.

    Mirrors :func:`requiresCompletionRequiredAsyncTaskWait`
    (``attempt.async-tasks.ts``).
    """
    return _REQUIRES_COMPLETION_REQUIRED_ASYNC_TASK_WAIT(dict(params or {}))


def should_wait_for_completion_required_async_tasks(
    params: Dict[str, Any],
) -> bool:
    """Return True when the attempt should wait for async tasks.

    Mirrors :func:`shouldWaitForCompletionRequiredAsyncTasks`
    (``attempt.async-tasks.ts``).
    """
    return _SHOULD_WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS(dict(params or {}))


async def wait_for_completion_required_async_tasks(
    params: Dict[str, Any],
) -> CompletionRequiredAsyncTaskWaitResult:
    """Wait for completion-required async tasks.

    Mirrors :func:`waitForCompletionRequiredAsyncTasks`
    (``attempt.async-tasks.ts``).
    """
    result: Any = await _maybe_await(
        _WAIT_FOR_COMPLETION_REQUIRED_ASYNC_TASKS(dict(params or {}))
    )
    if not isinstance(result, dict):
        result = {}
    return {
        "waited": bool(result.get("waited", True)),
        "completed": result.get("completed") or [],
        "remaining": result.get("remaining") or [],
    }


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


__all__ = [
    "AsyncStartedToolMeta",
    "CompletionRequiredAsyncTaskWaitResult",
    "requires_completion_required_async_task_wait",
    "set_requires_completion_required_async_task_wait_hook",
    "set_should_wait_for_completion_required_async_tasks_hook",
    "set_wait_for_completion_required_async_tasks_hook",
    "should_wait_for_completion_required_async_tasks",
    "wait_for_completion_required_async_tasks",
]
