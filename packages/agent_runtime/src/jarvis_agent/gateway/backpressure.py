"""Bounded backpressure queue and slow-client isolation for Track 3.4.

Enforces Invariant T34-22: Telemetry chunks may be dropped under high-water mark,
but authoritative structural transitions and verification evidence are strictly preserved.
"""

from __future__ import annotations

from collections import deque
import time

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.models import (
    EnrichedGatewayEvent,
    EventCategory,
)


class BackpressureQueue:
    """Per-connection bounded event queue isolating the scheduler from slow consumers."""

    def __init__(
        self,
        connection_id: str,
        capacity: int = 500,
        high_water_mark: int = 400,
        drain_timeout_seconds: float = 15.0,
    ) -> None:
        self.connection_id = connection_id
        self.capacity = capacity
        self.high_water_mark = high_water_mark
        self.drain_timeout_seconds = drain_timeout_seconds

        self._queue: deque[EnrichedGatewayEvent] = deque()
        self.dropped_telemetry_count: int = 0
        self._stalled_since: float | None = None

    def push(self, event: EnrichedGatewayEvent, now: float | None = None) -> bool:
        """Push event into connection queue applying Category-aware drop policy.

        Returns True if event was queued, False if dropped due to backpressure.
        Raises GatewayException(SLOW_DRAIN_TIMEOUT) if unrecoverably stalled.
        """
        curr_time = now if now is not None else time.monotonic()
        q_len = len(self._queue)

        if q_len >= self.capacity:
            if self._stalled_since is None:
                self._stalled_since = curr_time
            elif (curr_time - self._stalled_since) > self.drain_timeout_seconds:
                raise GatewayException(
                    code=GatewayErrorCode.SLOW_DRAIN_TIMEOUT,
                    message=f"Connection '{self.connection_id}' failed to drain queue within {self.drain_timeout_seconds}s timeout.",
                )

            # Try to evict an existing Category B telemetry event to make room for Category A/C
            if event.category != EventCategory.TELEMETRY:
                evicted = False
                for i in range(len(self._queue)):
                    if self._queue[i].category == EventCategory.TELEMETRY:
                        del self._queue[i]
                        self.dropped_telemetry_count += 1
                        evicted = True
                        break
                if evicted:
                    self._queue.append(event)
                    return True

            # If incoming event is telemetry and queue is full, drop it
            if event.category == EventCategory.TELEMETRY:
                self.dropped_telemetry_count += 1
                return False

            # Bounded overflow for critical events
            self._queue.append(event)
            return True

        # If over high-water mark, drop non-critical Category B telemetry
        if q_len >= self.high_water_mark and event.category == EventCategory.TELEMETRY:
            self.dropped_telemetry_count += 1
            return False

        self._queue.append(event)
        if q_len < self.high_water_mark:
            self._stalled_since = None
        return True

    def pop(self) -> EnrichedGatewayEvent | None:
        """Pop next event from queue."""
        if not self._queue:
            return None
        item = self._queue.popleft()
        if len(self._queue) < self.high_water_mark:
            self._stalled_since = None
        return item

    def __len__(self) -> int:
        return len(self._queue)


__all__ = ["BackpressureQueue"]
