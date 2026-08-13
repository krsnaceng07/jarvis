"""Async tool dispatch bridge — async counterpart to ToolDispatcher.

Provides `AsyncToolDispatcher` to execute plugin dispatch functions in
an async-friendly way. Sync plugin callables are offloaded to
`asyncio.to_thread`; async callables are awaited directly. Result
normalization mirrors `src.tools.dispatch.ToolDispatcher`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from src.tools.dispatch import PluginDispatchFn, ToolCallResult

_log = logging.getLogger("jarvis.tools.async_dispatch")


class AsyncToolDispatcher:
    """Async dispatcher that runs plugin dispatch functions safely.

    Accepts the same `plugin_dispatch` dict as `ToolDispatcher`.
    """

    def __init__(self, plugin_dispatch: dict[str, PluginDispatchFn]) -> None:
        self._dispatch = dict(plugin_dispatch)
        _log.info("async_tool_dispatcher: registered %d tool(s)", len(self._dispatch))

    def has(self, tool_name: str) -> bool:
        return tool_name in self._dispatch

    def registered_names(self) -> list[str]:
        return list(self._dispatch)

    async def execute(self, tool_name: str, args: dict[str, Any], *, call_id: str = "") -> ToolCallResult:
        """Execute a single tool call asynchronously.

        If the registered dispatch fn is a coroutine function it is awaited
        directly; otherwise it is executed in a thread via
        `asyncio.to_thread` to avoid blocking the event loop.
        """
        start = time.monotonic()
        fn = self._dispatch.get(tool_name)
        if fn is None:
            elapsed = int((time.monotonic() - start) * 1000)
            _log.warning("async_tool_dispatcher: unknown tool %r", tool_name)
            return ToolCallResult(
                tool_name=tool_name,
                call_id=call_id,
                content=f"Error: unknown tool '{tool_name}'. Available: {list(self._dispatch)}",
                is_error=True,
                duration_ms=elapsed,
            )

        try:
            # Run async functions inline, sync functions in a thread.
            if asyncio.iscoroutinefunction(fn):
                result = await fn(tool_name, args)
            else:
                result = await asyncio.to_thread(fn, tool_name, args)

            elapsed = int((time.monotonic() - start) * 1000)

            if result is None:
                content = "ok"
            elif isinstance(result, str):
                content = result
            else:
                try:
                    content = json.dumps(result, ensure_ascii=False, default=str)
                except (TypeError, ValueError):
                    content = str(result)

            _log.debug("async_tool_dispatcher: %s completed in %dms", tool_name, elapsed)
            return ToolCallResult(
                tool_name=tool_name,
                call_id=call_id,
                content=content,
                is_error=False,
                duration_ms=elapsed,
            )

        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - start) * 1000)
            _log.warning("async_tool_dispatcher: %s raised: %s", tool_name, exc)
            return ToolCallResult(
                tool_name=tool_name,
                call_id=call_id,
                content=f"Error: {type(exc).__name__}: {exc}",
                is_error=True,
                duration_ms=elapsed,
            )

    async def execute_batch(self, calls: list[dict[str, Any]]) -> list[ToolCallResult]:
        """Execute a batch of calls in order, awaiting each result."""
        out: list[ToolCallResult] = []
        for c in calls:
            res = await self.execute(c.get("name", ""), c.get("args", {}), call_id=c.get("id", ""))
            out.append(res)
        return out


__all__ = ["AsyncToolDispatcher"]
