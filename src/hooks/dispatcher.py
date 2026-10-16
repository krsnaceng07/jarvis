"""Internal Hook Dispatcher — runs operator-managed hook side effects.

Mirrors OpenClaw's internal hooks event dispatcher. It loads eligible
hooks via ``load_hooks()``, maps them to their ``handler.py`` callables,
and provides an async ``fire()`` method to dispatch ``InternalHookEvent``
to all matching handlers without blocking the gateway.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from collections import defaultdict
from typing import Any

from .loader import load_hook_handler, load_hooks
from .types import (
    HookEligibilityContext,
    HookEntry,
    InternalHookEvent,
    InternalHookHandler,
    is_known_hook_event_key,
)

_log = logging.getLogger("jarvis.hooks.dispatcher")


class InternalHookDispatcher:
    """Dispatches InternalHookEvent payloads to operator-managed hooks.

    Unlike ``HookBus`` (which runs plugin-provided callbacks synchronously
    or bounded-async in priority order), ``InternalHookDispatcher`` isolates
    side-effects like file logging, API calls, or git commits.

    It fires handlers in the background to ensure slow operator scripts
    never stall the agent loop.
    """

    def __init__(
        self,
        config: dict[str, Any],
        plugin_hook_dirs: list[dict[str, Any]] | None = None,
        eligibility: HookEligibilityContext | None = None,
    ) -> None:
        self._config = config
        self._plugin_hook_dirs = plugin_hook_dirs or []
        self._eligibility = eligibility or HookEligibilityContext()

        # event_key -> list of callables
        self._handlers_by_event: dict[str, list[InternalHookHandler]] = defaultdict(list)
        self._active_entries: list[HookEntry] = []

    def bootstrap(self) -> None:
        """Load and prepare all eligible hook handlers."""
        entries = load_hooks(
            plugin_hook_dirs=self._plugin_hook_dirs,
            config=self._config,
            eligibility=self._eligibility,
        )
        self._active_entries = entries

        for entry in entries:
            try:
                handler = load_hook_handler(entry)
            except Exception as e:
                _log.warning("failed to load hook %r handler: %s", entry.hook.name, e)
                continue

            metadata = entry.metadata
            if not metadata or not metadata.events:
                continue

            for ev in metadata.events:
                # The hook might subscribe to a specific key ("command:new") or a family ("command")
                if not is_known_hook_event_key(ev):
                    _log.warning("hook %r subscribed to unknown event %r", entry.hook.name, ev)

                self._handlers_by_event[ev].append(handler)

        _log.info("internal hooks dispatcher ready (%d active hooks)", len(self._active_entries))

    def _get_handlers_for(self, event_key: str) -> list[InternalHookHandler]:
        """Return all handlers listening to this event key or its family."""
        family = event_key.split(":")[0] if ":" in event_key else event_key
        handlers = list(self._handlers_by_event.get(family, []))
        if family != event_key:
            handlers.extend(self._handlers_by_event.get(event_key, []))
        return handlers

    async def _run_handler_safe(
        self, handler: InternalHookHandler, event: InternalHookEvent
    ) -> None:
        """Execute a single handler, logging any exceptions."""
        try:
            res = handler(event)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            _log.error("internal hook %r failed: %s", handler, e)
            traceback.print_exc()

    def fire(self, event: InternalHookEvent) -> None:
        """Dispatch an event to all matching hooks.

        This is fire-and-forget. It schedules background tasks on the running loop.
        For shutdown events, you may want to wait for pending tasks.
        """
        handlers = self._get_handlers_for(event.event_key)
        if not handlers:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # If there's no loop, run them blocking (useful in tests)
            asyncio.run(self._fire_blocking(handlers, event))
            return

        loop.create_task(self._fire_blocking(handlers, event))

    async def _fire_blocking(
        self, handlers: list[InternalHookHandler], event: InternalHookEvent
    ) -> None:
        """Run handlers sequentially in a blocking manner."""
        for handler in handlers:
            await self._run_handler_safe(handler, event)

    async def fire_and_wait(self, event: InternalHookEvent, timeout_s: float = 5.0) -> None:
        """Dispatch an event and wait for handlers to complete, up to a timeout.

        Used for lifecycle events like gateway:shutdown or gateway:pre-restart
        where the process might exit shortly after.
        """
        handlers = self._get_handlers_for(event.event_key)
        if not handlers:
            return

        try:
            await asyncio.wait_for(self._fire_blocking(handlers, event), timeout=timeout_s)
        except asyncio.TimeoutError:
            _log.warning("internal hook handlers timed out for %r", event.event_key)


_global_dispatcher: InternalHookDispatcher | None = None


def set_global_dispatcher(dispatcher: InternalHookDispatcher) -> None:
    """Set the global internal hook dispatcher for this process."""
    global _global_dispatcher
    _global_dispatcher = dispatcher


def get_global_dispatcher() -> InternalHookDispatcher | None:
    """Get the global internal hook dispatcher if initialized."""
    return _global_dispatcher
