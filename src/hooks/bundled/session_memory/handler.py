"""Bundled session-memory hook — mirrors OpenClaw ``bundled/session-memory``.

Fires on ``session:start`` and ``agent:bootstrap`` to inject the operator's
active memory context (from the active MemoryHostPlugin) into the event's
messages list. The channel session runner reads these messages and prepends
them to the system prompt for the turn.
"""

from __future__ import annotations

import logging

_log = logging.getLogger("jarvis.hooks.bundled.session_memory")


def handle(event) -> None:  # type: ignore[no-untyped-def]
    """Inject memory context into the session start event.

    The hook appends a memory summary to ``event.messages`` which the
    host reads as extra system-prompt material for the first turn.
    """
    try:
        # Lazy import to avoid circular deps at load time
        from src.memory import get_active_memory_context  # type: ignore[import-not-found]
        context = get_active_memory_context()
        if context:
            event.messages.append(context)
            _log.debug("session-memory: injected %d chars", len(context))
    except ImportError:
        # Memory subsystem not yet available — no-op
        pass
    except Exception as e:  # noqa: BLE001
        _log.debug("session-memory hook failed: %s", e)
