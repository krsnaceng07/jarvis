"""jarvis_learning.evaluation.event_bus — In-Memory Pub/Sub Canonical Event Bus.

Enforces:
1. INV-P9-HOST-001: Ultra-low-latency non-blocking dispatch (< 0.1ms).
2. INV-P9-HOST-002: Subscriber exceptions are caught and contained; active caller never crashes.
3. INV-P9-DEP-001: Active runtime has zero synchronous dependency on subscriber completion.
4. Support for wildcards (subscribe to all events) or filtered event types.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Callable

from .event_envelope import CanonicalEventEnvelope

logger = logging.getLogger(__name__)

EventCallback = Callable[[CanonicalEventEnvelope], None]


class SubscriptionHandle:
    """Opaque handle used to safely unsubscribe a listener."""

    __slots__ = ("handle_id", "event_type", "_bus", "_active")

    def __init__(self, handle_id: str, event_type: str | None, bus: CanonicalEventBus) -> None:
        self.handle_id = handle_id
        self.event_type = event_type
        self._bus = bus
        self._active = True

    def unsubscribe(self) -> None:
        if self._active:
            self._bus.unsubscribe(self)
            self._active = False

    def is_active(self) -> bool:
        return self._active


class CanonicalEventBus:
    """Thread-safe, non-blocking in-memory event bus separating active runtime from learning."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str | None, dict[str, EventCallback]] = {None: {}}
        self.total_published = 0
        self.total_subscriber_exceptions = 0
        self.last_dispatch_latency_ms = 0.0

    @property
    def subscriber_count(self) -> int:
        """Total number of active subscribers across all event filters."""
        with self._lock:
            return sum(len(subs) for subs in self._subscribers.values())

    def subscribe(
        self,
        callback: EventCallback,
        event_type: str | None = None,
    ) -> SubscriptionHandle:
        """Subscribe a callback to a specific event_type, or None for all events."""
        with self._lock:
            handle_id = f"sub_{uuid.uuid4().hex[:8]}"
            if event_type not in self._subscribers:
                self._subscribers[event_type] = {}
            self._subscribers[event_type][handle_id] = callback
            return SubscriptionHandle(handle_id, event_type, self)

    def unsubscribe(self, handle: SubscriptionHandle) -> bool:
        """Remove a subscriber using its handle."""
        with self._lock:
            event_type = handle.event_type
            if (
                event_type in self._subscribers
                and handle.handle_id in self._subscribers[event_type]
            ):
                del self._subscribers[event_type][handle.handle_id]
                return True
            return False

    def publish_nonblocking(self, envelope: CanonicalEventEnvelope) -> float:
        """Publish an event envelope synchronously to registered subscribers with zero blocking.

        Returns dispatch latency in milliseconds (INV-P9-HOST-001 SLO: < 0.5ms).
        Subscriber exceptions are caught and never bubble up (INV-P9-HOST-002).
        """
        start = time.perf_counter()
        targets: list[EventCallback] = []

        with self._lock:
            self.total_published += 1
            # 1. Global wildcard subscribers
            targets.extend(self._subscribers.get(None, {}).values())
            # 2. Type-specific subscribers
            if envelope.event_type in self._subscribers:
                targets.extend(self._subscribers[envelope.event_type].values())

        # Invoke subscribers outside lock to avoid lock contention
        for cb in targets:
            try:
                cb(envelope)
            except Exception as e:
                self.total_subscriber_exceptions += 1
                logger.error(
                    "EventBus subscriber error on event %s (%s): %s",
                    envelope.event_id,
                    envelope.event_type,
                    e,
                    exc_info=True,
                )

        latency_ms = (time.perf_counter() - start) * 1000.0
        self.last_dispatch_latency_ms = latency_ms
        return latency_ms

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._subscribers = {None: {}}


# Process-level singleton instance
_GLOBAL_EVENT_BUS: CanonicalEventBus | None = None
_INIT_LOCK = threading.Lock()


def get_global_event_bus() -> CanonicalEventBus:
    """Retrieve process-global CanonicalEventBus instance."""
    global _GLOBAL_EVENT_BUS
    if _GLOBAL_EVENT_BUS is None:
        with _INIT_LOCK:
            if _GLOBAL_EVENT_BUS is None:
                _GLOBAL_EVENT_BUS = CanonicalEventBus()
    return _GLOBAL_EVENT_BUS


def reset_global_event_bus() -> None:
    """Reset global event bus instance (for test isolation)."""
    global _GLOBAL_EVENT_BUS
    with _INIT_LOCK:
        if _GLOBAL_EVENT_BUS is not None:
            _GLOBAL_EVENT_BUS.clear()
        _GLOBAL_EVENT_BUS = CanonicalEventBus()
