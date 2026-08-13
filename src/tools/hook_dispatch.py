"""Hook-aware ToolDispatcher — fires TOOL_CALLED and TOOL_COMPLETED hooks.

W3.2 wrapper: thin subclass of ``ToolDispatcher`` that accepts an optional
``HookBus`` and fires ``tool_called`` before each dispatch and
``tool_completed`` after. If no bus is provided, behaviour is identical
to the base class.

Mirrors OpenClaw's ``src/tools/hook-aware-dispatch.ts``.
"""

from __future__ import annotations

import logging
from typing import Any

from src.tools.dispatch import PluginDispatchFn, ToolCallResult, ToolDispatcher

_log = logging.getLogger("jarvis.tools.hook_dispatch")


class HookAwareToolDispatcher(ToolDispatcher):
    """Fires TOOL_CALLED / TOOL_COMPLETED hooks around each tool execution.

    Parameters
    ----------
    plugin_dispatch : dict[str, PluginDispatchFn]
        Tool name → dispatch fn mapping.
    bus : HookBus | None
        If None, no hooks are fired (same as base class).
    """

    def __init__(
        self,
        plugin_dispatch: dict[str, PluginDispatchFn],
        bus: Any | None = None,
    ) -> None:
        super().__init__(plugin_dispatch)
        self._bus = bus

    def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        call_id: str = "",
    ) -> ToolCallResult:
        """Execute a tool call, firing hooks before and after."""
        if self._bus is not None:
            _fire_sync_safe(
                self._bus,
                "tool_called",
                {"tool": tool_name, "args": args, "call_id": call_id},
            )

        result = super().execute(tool_name, args, call_id=call_id)

        if self._bus is not None:
            _fire_sync_safe(
                self._bus,
                "tool_completed",
                {
                    "tool": tool_name,
                    "call_id": call_id,
                    "is_error": result.is_error,
                    "duration_ms": result.duration_ms,
                },
            )

        return result


def _fire_sync_safe(bus: Any, name: str, payload: Any) -> None:
    """Call ``fire_sync(bus, name, payload)`` without raising."""
    try:
        from src.hooks import fire_sync
        fire_sync(bus, name, payload)
    except Exception as e:  # noqa: BLE001
        _log.debug("hook_dispatch: fire_sync %r failed: %s", name, e)


__all__ = ["HookAwareToolDispatcher"]
