"""Plugin event bus — mirrors OpenClaw's ``src/hooks/`` system.

The host fires events at well-defined points in the agent loop
(``before_agent_start``, ``agent_end``, ``message_received``, ...).
Every registered handler runs in priority order. The bus is
fire-and-forget by default; a per-handler ``timeout_ms`` caps how
long the host will wait.

Mirrors OpenClaw's ``src/hooks/internal-hook-types.ts`` + the
``api.on(hookName, handler, opts)`` registration surface.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections import defaultdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jarvis_sdk import HookRegistration

_log = logging.getLogger("src.hooks")


class HookBus:
    """In-process pub/sub for plugin event handlers.

    Phase 2 host. The host creates one ``HookBus`` per session and
    merges every plugin's ``HookRegistration`` from ``_load_plugins()``
    into it. Events are dispatched in priority order (highest first).
    Per-handler exceptions are logged but do not stop the bus.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[HookRegistration]] = defaultdict(list)

    def register(self, registration: HookRegistration) -> None:
        """Add a handler. Sorted on dispatch, not on insert."""
        if not callable(registration.handler):
            raise TypeError(f"HookRegistration({registration.name!r}).handler must be callable")
        self._handlers[registration.name].append(registration)

    def register_all(self, registrations: list[HookRegistration]) -> None:
        for r in registrations:
            self.register(r)

    def handlers_for(self, name: str) -> list[HookRegistration]:
        """Return sorted handlers for an event (highest priority first)."""
        return sorted(
            self._handlers.get(name, []),
            key=lambda r: r.priority,
            reverse=True,
        )

    def names(self) -> list[str]:
        """All event names that have at least one handler."""
        return sorted(self._handlers.keys())

    def count(self, name: str | None = None) -> int:
        if name is None:
            return sum(len(h) for h in self._handlers.values())
        return len(self._handlers.get(name, []))

    async def fire(self, name: str, payload: Any = None) -> None:
        """Fire an event. Each handler is awaited (or fire-and-forget).

        Exceptions in a handler are logged + traceback-printed; the
        bus keeps dispatching to remaining handlers. This mirrors
        OpenClaw's "never let a hook break the agent loop" rule.
        """
        handlers = self.handlers_for(name)
        if not handlers:
            return
        for reg in handlers:
            try:
                coro_or_value = reg.handler(payload)
                if asyncio.iscoroutine(coro_or_value):
                    if reg.timeout_ms is not None:
                        await asyncio.wait_for(coro_or_value, timeout=reg.timeout_ms / 1000.0)
                    else:
                        await coro_or_value
            except TimeoutError:
                _log.warning(
                    "hook %s for %s timed out after %sms",
                    reg.handler,
                    name,
                    reg.timeout_ms,
                )
            except Exception as e:
                _log.warning("hook %s for %s failed: %s", reg.handler, name, e)
                traceback.print_exc()


# ── Synchronous helper (for non-async hosts) ─────────────────────────


def fire_sync(bus: HookBus, name: str, payload: Any = None) -> None:
    """Synchronous fire — used by non-async host code paths.

    Runs the event loop to completion. Safe to call from inside an
    async function (we detect the running loop and use
    ``run_coroutine_threadsafe``-style behavior).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running loop — use asyncio.run (blocks until done).
        asyncio.run(bus.fire(name, payload))
        return
    # Inside an async context: just create a task and return None —
    # the caller can await the task if it cares.
    _ = loop.create_task(bus.fire(name, payload))  # noqa: RUF006 (fire-and-forget)
    return


__all__ = ["HookBus", "fire_sync"]
