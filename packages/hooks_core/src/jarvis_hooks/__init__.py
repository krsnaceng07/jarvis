"""jarvis_hooks — JARVIS plugin event bus.

Re-exports :class:`~src.hooks.HookBus` and :func:`~src.hooks.fire_sync`
from ``src/hooks/`` as the canonical ``jarvis_hooks`` package surface.

The bus fires events at well-defined points in the agent loop.
Plugins register handlers via ``api.register_hook(name, handler)``
and the host wires them in after discovery:

    result = load_all_plugins_from_workspace(workspace)
    bus = HookBus()
    bus.register_all(result.hooks)

Hook names mirror OpenClaw's ``src/hooks/hook-types.ts``:

- ``before_agent_start``
- ``agent_end``
- ``message_received``
- ``message_sent``
- ``tool_called``
- ``tool_completed``
- ``session_start``
- ``session_end``
"""

from __future__ import annotations

from enum import Enum

# Re-export from src.hooks (the implementation lives there until Phase 6
# when hooks_core absorbs it fully and src/hooks becomes a thin shim).
from src.hooks import HookBus, fire_sync


# ── Typed hook name enum (W8.2) ────────────────────────────────────────
# Mirrors OpenClaw's ``PluginHookName`` from
# ``packages/hooks-core/src/hook-types.ts``.
# Inheriting from str means the enum values compare equal to plain
# strings, so existing ``bus.fire("tool_called", ...)`` calls keep
# working without any migration.


class HookName(str, Enum):
    """Typed hook name enum — safe alternative to raw string constants.

    Usage::

        bus.fire(HookName.TOOL_CALLED, payload)

    Backward-compatible with raw string names because ``HookName``
    inherits from ``str`` and the values equal the legacy constants.
    """

    BEFORE_AGENT_START = "before_agent_start"
    AGENT_END = "agent_end"
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    TOOL_CALLED = "tool_called"
    TOOL_COMPLETED = "tool_completed"
    SESSION_START = "session_start"
    SESSION_END = "session_end"


# ── Legacy string constants (kept for backward compat) ─────────────────
# New plugin code should prefer ``HookName.TOOL_CALLED`` etc.
BEFORE_AGENT_START = HookName.BEFORE_AGENT_START.value
AGENT_END = HookName.AGENT_END.value
MESSAGE_RECEIVED = HookName.MESSAGE_RECEIVED.value
MESSAGE_SENT = HookName.MESSAGE_SENT.value
TOOL_CALLED = HookName.TOOL_CALLED.value
TOOL_COMPLETED = HookName.TOOL_COMPLETED.value
SESSION_START = HookName.SESSION_START.value
SESSION_END = HookName.SESSION_END.value

__all__ = [
    # Bus
    "HookBus",
    "HookName",
    "fire_sync",
    # Legacy string constants (backward compat)
    "BEFORE_AGENT_START",
    "AGENT_END",
    "MESSAGE_RECEIVED",
    "MESSAGE_SENT",
    "TOOL_CALLED",
    "TOOL_COMPLETED",
    "SESSION_START",
    "SESSION_END",
]
