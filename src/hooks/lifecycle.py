"""Hook lifecycle dispatcher — fires agent lifecycle hooks.

Mirrors OpenClaw's ``src/hooks/lifecycle.ts`` +
``src/hooks/session-lifecycle-hooks.ts``.

The ``LifecycleHooks`` class wraps a ``HookBus`` and provides named
methods that the host calls at the canonical lifecycle points:

  - ``on_session_start(info)``   — fired when a new agent session opens
  - ``on_session_end(info)``     — fired when a session closes
  - ``on_message_received(msg)`` — fired when a user message arrives
  - ``on_message_sent(reply)``   — fired after the agent reply is sent
  - ``on_before_agent_start()``  — fired before the first agent turn
  - ``on_agent_end(outcome)``    — fired after the last agent turn

All firings are fire-and-forget (``fire_sync``). The host does not
wait for hook handlers to complete before continuing.
"""

from __future__ import annotations

import logging
from typing import Any

# W8.3: use typed HookName instead of raw strings.
from jarvis_hooks import HookName

_log = logging.getLogger("jarvis.hooks.lifecycle")


class LifecycleHooks:
    """Named lifecycle hook dispatch wrapper.

    Accepts ``None`` as bus for no-op mode (useful when no plugins are
    loaded or in tests).
    """

    def __init__(self, bus: Any | None) -> None:
        self._bus = bus

    def _fire(self, name: HookName | str, payload: Any = None) -> None:
        if self._bus is None:
            return
        try:
            from src.hooks import fire_sync
            fire_sync(self._bus, name, payload)
        except Exception as e:  # noqa: BLE001
            _log.debug("lifecycle: fire %r failed: %s", name, e)

    def on_session_start(self, info: dict[str, Any] | None = None) -> None:
        """Fired when a new agent session opens."""
        self._fire(HookName.SESSION_START, info or {})

    def on_session_end(self, info: dict[str, Any] | None = None) -> None:
        """Fired when a session closes."""
        self._fire(HookName.SESSION_END, info or {})

    def on_message_received(self, message: Any) -> None:
        """Fired when a user message arrives (channel or voice)."""
        self._fire(HookName.MESSAGE_RECEIVED, message)

    def on_message_sent(self, reply: Any) -> None:
        """Fired after the agent reply is sent."""
        self._fire(HookName.MESSAGE_SENT, reply)

    def on_before_agent_start(self, context: Any = None) -> None:
        """Fired before the first agent turn starts."""
        self._fire(HookName.BEFORE_AGENT_START, context)

    def on_agent_end(self, outcome: Any = None) -> None:
        """Fired after the last agent turn completes."""
        self._fire(HookName.AGENT_END, outcome)


__all__ = ["LifecycleHooks"]
