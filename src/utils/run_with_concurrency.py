"""jarvis.utils.run_with_concurrency — bounded worker-pool task runner.

OpenClaw parity: mirrors ``openclaw-main/src/utils/run-with-concurrency.ts``.

Public surface:

- :class:`ConcurrencyErrorMode`
- :func:`run_tasks_with_concurrency`
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, List


ConcurrencyErrorMode = str  # "continue" | "stop"


async def run_tasks_with_concurrency(params: dict) -> dict:
    """Run async task factories with bounded concurrency, preserving result indexes.

    Mirrors :func:`runTasksWithConcurrency` (``utils/run-with-concurrency.ts``).
    """
    tasks = params.get("tasks") or []
    if not tasks:
        return {"results": [], "firstError": None, "hasError": False}
    limit = params.get("limit")
    error_mode = params.get("errorMode") or "continue"
    on_task_error = params.get("onTaskError")
    if isinstance(limit, (int, float)) and limit == limit:
        resolved_limit = max(1, min(int(limit), len(tasks)))
    else:
        resolved_limit = len(tasks)
    results: List[Any] = [None] * len(tasks)
    first_error: Any = None
    has_error = False
    semaphore = asyncio.Semaphore(resolved_limit)

    async def _run_one(index: int, factory: Callable[[], Awaitable[Any]]) -> None:
        nonlocal first_error, has_error
        if error_mode == "stop" and has_error:
            return
        async with semaphore:
            if error_mode == "stop" and has_error:
                return
            try:
                results[index] = await factory()
            except Exception as exc:
                if not has_error:
                    first_error = exc
                    has_error = True
                if callable(on_task_error):
                    try:
                        on_task_error(exc, index)
                    except Exception:
                        pass

    await asyncio.gather(
        *[_run_one(i, t) for i, t in enumerate(tasks)],
        return_exceptions=True,
    )
    return {
        "results": results,
        "firstError": first_error,
        "hasError": has_error,
    }


__all__ = [
    "ConcurrencyErrorMode",
    "run_tasks_with_concurrency",
]
