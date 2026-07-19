"""Hook types — the plugin event bus.

Mirrors OpenClaw's ``src/hooks/`` event-bus. Plugins register handlers
for named events (``api.register_hook(name, handler)``); the host
fires events at well-defined points in the agent loop and the bus
dispatches to every subscriber in order.

Canonical hook names (mirror OpenClaw's
``src/hooks/hook-types.ts``):

  - ``before_agent_start`` — fired before the agent sees a new turn.
  - ``agent_end`` — fired after the agent turn completes.
  - ``message_received`` — fired on inbound channel messages.
  - ``message_sent`` — fired on outbound channel messages.
  - ``tool_called`` — fired before/after every tool invocation.
  - ``session_start`` — fired when a session is created.
  - ``session_end`` — fired when a session closes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# Canonical hook names. Mirrors OpenClaw's `PluginHookName` enum.
HookName = Literal[
    "before_agent_start",
    "agent_end",
    "message_received",
    "message_sent",
    "tool_called",
    "tool_completed",
    "session_start",
    "session_end",
]


@dataclass(frozen=True, slots=True)
class HookRegistration:
    """A plugin-registered hook handler.

    Attributes
    ----------
    name : str
        The event name (e.g. ``"before_agent_start"``).
    handler : Callable
        The async function invoked when the event fires. Receives
        the event payload as its single argument.
    priority : int
        Higher = earlier. Default 0. Mirrors OpenClaw's
        ``opts.priority`` parameter.
    timeout_ms : int | None
        Optional per-handler timeout. Mirrors OpenClaw's
        ``opts.timeoutMs`` parameter.
    """

    name: str
    handler: Callable[..., Any]
    priority: int = 0
    timeout_ms: int | None = None


#: Async handler signature: ``async (event) -> None``.
HookHandler = Callable[..., Any]


__all__ = ["HookHandler", "HookName", "HookRegistration"]
