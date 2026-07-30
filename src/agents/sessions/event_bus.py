"""jarvis.agents.sessions.event_bus — tiny event bus abstraction.

OpenClaw parity: mirrors
``openclaw-main/src/agents/sessions/event-bus.ts``.

Isolates handler failures so one bad subscriber cannot
break later listeners.

Parity
======
- ``EventBus`` protocol with ``emit(channel, data)`` and
  ``on(channel, handler) -> unsubscriber``
  (``event-bus.ts:9-12``).
- ``EventBusController`` extends ``EventBus`` with
  ``clear()`` (``event-bus.ts:15-17``).
- ``create_event_bus() -> EventBusController``
  (``event-bus.ts:20-42``) — wraps an in-process
  emitter with try/except isolation so a handler
  exception logs and keeps the bus alive.
- The Python port uses ``threading``-backed fan-out
  rather than ``node:events`` because Python has no
  equivalent in the standard library. Same semantics:
  multiple subscribers receive every event; ordering
  follows subscription order.

Phase 6.0 — scaffolding + helpers + small types.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Protocol, runtime_checkable


_LOG = logging.getLogger("jarvis.agents.sessions.event_bus")


@runtime_checkable
class EventBus(Protocol):
    """Minimal publish/subscribe interface used by
    session components. Mirrors ``EventBus``
    (``event-bus.ts:9-12``)."""

    def emit(self, channel: str, data: object) -> None:
        """Publish ``data`` to every subscriber of
        ``channel``. Returns immediately."""
        ...

    def on(
        self, channel: str, handler: Callable[[object], None]
    ) -> Callable[[], None]:
        """Subscribe ``handler`` to ``channel``. Returns
        an unsubscribe callable."""
        ...


@runtime_checkable
class EventBusController(EventBus, Protocol):
    """Event bus plus lifecycle control for tests and
    teardown. Mirrors ``EventBusController``
    (``event-bus.ts:15-17``)."""

    def clear(self) -> None:
        """Remove every subscriber from every channel."""
        ...


#: Subscriber handle. ``True`` means subscribed; calling
#: the function unsubscribes the listener.
Subscriber = Callable[[], None]


def create_event_bus() -> EventBusController:
    """Create an in-process event bus with unsubscribe
    and clear support.

    Mirrors ``createEventBus`` (``event-bus.ts:20-42``).

    The returned object isolates handler failures via a
    try/except wrapper so one bad subscriber cannot
    break later listeners — matches the OpenClaw
    comment "Isolates handler failures so one bad
    subscriber cannot break later listeners." Errors
    are logged via ``logging`` instead of
    ``console.error`` (Python convention).
    """
    # Use a list of (channel, handler) tuples for
    # ordered, thread-safe fan-out. ``threading.Lock``
    # guards mutation; reads hold the lock briefly to
    # build a snapshot list before invoking handlers.
    subscribers: list[tuple[str, Callable[[object], None]]] = []
    lock = threading.Lock()

    def emit(channel: str, data: object) -> None:
        with lock:
            # Build a snapshot of matching subscribers
            # so handler side-effects (subscribe /
            # unsubscribe) don't perturb the iteration.
            pending = [
                handler
                for (ch, handler) in subscribers
                if ch == channel
            ]
        for handler in pending:
            try:
                handler(data)
            except Exception:
                # Session event handlers are observers;
                # log and keep the bus alive.
                _LOG.exception(
                    "Event handler error (channel=%s)", channel
                )

    def on(
        channel: str, handler: Callable[[object], None]
    ) -> Subscriber:
        def safe_handler(data: object) -> None:
            try:
                handler(data)
            except Exception:
                _LOG.exception(
                    "Event handler error (channel=%s)", channel
                )

        with lock:
            subscribers.append((channel, safe_handler))
            idx = len(subscribers) - 1

        def unsubscribe() -> None:
            with lock:
                # Replace with a sentinel so other
                # subscribers aren't shifted. The
                # snapshot in ``emit`` still works.
                subscribers[idx] = (channel, _SENTINEL_HANDLER)

        return unsubscribe

    def clear() -> None:
        with lock:
            subscribers.clear()

    return _EventBusControllerImpl(emit=emit, on=on, clear=clear)


async def _SENTINEL_HANDLER(_data: object) -> None:  # pragma: no cover
    """Sentinel used by ``unsubscribe`` so a removed
    listener's slot stays a valid callable for the
    snapshot iteration in ``emit``."""


class _EventBusControllerImpl:
    """Concrete ``EventBusController``. Plain class
    rather than a dataclass because the bound methods
    reference the closure-local ``subscribers`` / ``lock``
    — a dataclass would either require those as fields
    (no behaviour advantage) or break the closure
    capture.

    The class is a private implementation detail; the
    public type is ``EventBusController``.
    """

    __slots__ = ("emit", "on", "clear")

    def __init__(
        self,
        *,
        emit: Callable[[str, object], None],
        on: Callable[[str, Callable[[object], None]], Subscriber],
        clear: Callable[[], None],
    ) -> None:
        self.emit = emit
        self.on = on
        self.clear = clear


__all__ = [
    "EventBus",
    "EventBusController",
    "Subscriber",
    "create_event_bus",
]
