"""Async, hook-aware tool dispatcher.

Wraps :class:`src.tools.async_dispatch.AsyncToolDispatcher` and fires
async hook events on the provided :class:`src.hooks.HookBus`.
"""
from __future__ import annotations

import logging
from typing import Any

from src.hooks import HookBus
from src.tools.async_dispatch import AsyncToolDispatcher
from src.tools.dispatch import ToolCallResult

_log = logging.getLogger("jarvis.tools.hook_async_dispatch")


class HookAwareAsyncToolDispatcher(AsyncToolDispatcher):
    """Async dispatcher that fires `tool_called` and `tool_completed` hooks.

    The hooks are awaited (via the bus.fire coroutine) so handlers may be
    async or sync. Exceptions in hook handlers are caught and logged.
    """

    def __init__(self, plugin_dispatch: dict[str, Any], bus: HookBus | None = None) -> None:
        super().__init__(plugin_dispatch)
        self._bus = bus

    async def execute(self, tool_name: str, args: dict[str, Any], *, call_id: str = "") -> ToolCallResult:
        if self._bus is not None:
            try:
                await self._bus.fire("tool_called", {"tool": tool_name, "args": args, "call_id": call_id})
            except Exception as e:  # pragma: no cover - defensive
                _log.debug("hook_async_dispatch: tool_called hook failed: %s", e)

        result = await super().execute(tool_name, args, call_id=call_id)

        if self._bus is not None:
            try:
                await self._bus.fire(
                    "tool_completed",
                    {
                        "tool": tool_name,
                        "call_id": call_id,
                        "is_error": result.is_error,
                        "duration_ms": result.duration_ms,
                    },
                )
            except Exception as e:  # pragma: no cover - defensive
                _log.debug("hook_async_dispatch: tool_completed hook failed: %s", e)

        return result


__all__ = ["HookAwareAsyncToolDispatcher"]
