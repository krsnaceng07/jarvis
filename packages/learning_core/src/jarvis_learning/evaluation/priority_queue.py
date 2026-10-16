"""jarvis_learning.evaluation.priority_queue — Priority-Aware Non-Interference Shadow Queue.

Enforces:
1. INV-P9-HOST-001: Ultra-fast local enqueue latency (p50 <= 0.5ms, p95 <= 2ms).
2. Priority-aware load shedding:
   - P0_CRITICAL: Never silently dropped; emergency fallback log & buffer on overload.
   - P1_HIGH: Strongly protected (sheds only at >=95% capacity).
   - P2_NORMAL: Sheds at >=80% capacity.
   - P3_LOW: First to drop (sheds at >=60% capacity).
3. INV-P9-OBS-001: Explicit SHADOW_EVENT_DROPPED emission with reason and priority.
4. INV-P9-OBS-002: Sampling completeness metrics and bias warning detection.
"""

from __future__ import annotations

import collections
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .event_envelope import CanonicalEventEnvelope, EventPriority

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DroppedEventRecord:
    """Audit record for any dropped event."""

    event_id: str
    event_type: str
    priority: str
    reason: str
    queue_depth: int
    timestamp_mono: float = field(default_factory=time.monotonic)


@dataclass(frozen=True, slots=True)
class SamplingCompletenessMetrics:
    """Metrics tracking queue retention vs shedding across priority classes."""

    total_enqueued: int
    total_retained: int
    total_dropped: int
    dropped_by_priority: dict[str, int]
    completeness_ratio: float  # retained / enqueued
    sampling_bias_warning: bool
    bias_reason: str = ""


class PriorityShadowQueue:
    """Bounded, priority-aware queue ensuring zero active thread blocking."""

    def __init__(
        self,
        max_capacity: int = 1000,
        emergency_log_path: Path | str | None = None,
    ) -> None:
        self.max_capacity = max_capacity
        self.emergency_log_path = Path(emergency_log_path or "emergency_safety.log")
        self._lock = threading.Lock()
        self._queue: collections.deque[CanonicalEventEnvelope] = collections.deque(
            maxlen=max_capacity
        )
        self._emergency_buffer: list[CanonicalEventEnvelope] = []

        self.total_enqueued = 0
        self.total_dropped = 0
        self.dropped_by_priority: dict[str, int] = {
            EventPriority.P0_CRITICAL: 0,
            EventPriority.P1_HIGH: 0,
            EventPriority.P2_NORMAL: 0,
            EventPriority.P3_LOW: 0,
        }
        self.recent_dropped: list[DroppedEventRecord] = []
        self.last_enqueue_latency_ms = 0.0

    def enqueue(self, envelope: CanonicalEventEnvelope) -> bool:
        """Enqueue an event with priority-based admission control.

        SLO: p50 <= 0.5ms, p95 <= 2ms. Never raises exceptions.
        """
        start = time.perf_counter()
        prio = envelope.priority
        admitted = False

        with self._lock:
            self.total_enqueued += 1
            current_len = len(self._queue)
            capacity_ratio = current_len / max(1, self.max_capacity)

            # Admission check based on priority tier
            if prio == EventPriority.P0_CRITICAL:
                # P0 is never silently discarded
                if current_len < self.max_capacity:
                    self._queue.append(envelope)
                    admitted = True
                else:
                    # Emergency persistence fallback chain
                    admitted = self._handle_emergency_p0(envelope, current_len)
            elif prio == EventPriority.P1_HIGH:
                if capacity_ratio < 0.95:
                    self._queue.append(envelope)
                    admitted = True
                else:
                    self._record_drop(envelope, "SHED_P1_AT_95_PCT", current_len)
            elif prio == EventPriority.P2_NORMAL:
                if capacity_ratio < 0.80:
                    self._queue.append(envelope)
                    admitted = True
                else:
                    self._record_drop(envelope, "SHED_P2_AT_80_PCT", current_len)
            else:  # P3_LOW
                if capacity_ratio < 0.60:
                    self._queue.append(envelope)
                    admitted = True
                else:
                    self._record_drop(envelope, "SHED_P3_AT_60_PCT", current_len)

        latency_ms = (time.perf_counter() - start) * 1000.0
        self.last_enqueue_latency_ms = latency_ms
        return admitted

    def _handle_emergency_p0(self, envelope: CanonicalEventEnvelope, current_len: int) -> bool:
        """Fallback chain for P0 events when primary queue is saturated."""
        self._emergency_buffer.append(envelope)
        # Attempt emergency append to disk without blocking
        try:
            with open(self.emergency_log_path, "a", encoding="utf-8") as f:
                f.write(envelope.to_json() + "\n")
            logger.critical(
                "EMERGENCY_PERSISTENCE_WRITTEN: P0 event %s written to fallback log",
                envelope.event_id,
            )
            return True
        except Exception as e:
            logger.critical(
                "CRITICAL_PERSISTENCE_FAILURE: Could not write P0 event %s to fallback log: %e",
                envelope.event_id,
                e,
            )
            self._record_drop(envelope, "EMERGENCY_DISK_FAILED", current_len)
            return False

    def _record_drop(self, envelope: CanonicalEventEnvelope, reason: str, queue_depth: int) -> None:
        """Record an explicit drop event for observability."""
        self.total_dropped += 1
        prio_key = envelope.priority
        if prio_key in self.dropped_by_priority:
            self.dropped_by_priority[prio_key] += 1
        else:
            self.dropped_by_priority[prio_key] = 1

        rec = DroppedEventRecord(
            event_id=envelope.event_id,
            event_type=envelope.event_type,
            priority=envelope.priority,
            reason=reason,
            queue_depth=queue_depth,
        )
        self.recent_dropped.append(rec)
        if len(self.recent_dropped) > 100:
            self.recent_dropped.pop(0)

        logger.warning(
            "SHADOW_EVENT_DROPPED: id=%s type=%s prio=%s reason=%s depth=%d",
            envelope.event_id,
            envelope.event_type,
            envelope.priority,
            reason,
            queue_depth,
        )

    def pop_batch(self, max_items: int = 50) -> list[CanonicalEventEnvelope]:
        """Retrieve batch of items for background worker dispatch."""
        with self._lock:
            batch: list[CanonicalEventEnvelope] = []
            while self._queue and len(batch) < max_items:
                batch.append(self._queue.popleft())
            return batch

    def get_completeness_metrics(self) -> SamplingCompletenessMetrics:
        """Compute sampling completeness ratio and bias indicators (INV-P9-OBS-002)."""
        with self._lock:
            retained = len(self._queue) + (
                self.total_enqueued - self.total_dropped - len(self._queue)
            )
            ratio = retained / max(1, self.total_enqueued) if self.total_enqueued > 0 else 1.0

            # Bias warning if P0 or P1 drops occurred, or overall completeness < 75%
            has_p0_drops = self.dropped_by_priority.get(EventPriority.P0_CRITICAL, 0) > 0
            has_p1_drops = self.dropped_by_priority.get(EventPriority.P1_HIGH, 0) > 0
            low_completeness = ratio < 0.75 and self.total_enqueued >= 20

            bias_warning = has_p0_drops or has_p1_drops or low_completeness
            bias_reason = ""
            if has_p0_drops:
                bias_reason = "CRITICAL_P0_EVENTS_DROPPED"
            elif has_p1_drops:
                bias_reason = "HIGH_PRIORITY_P1_EVENTS_DROPPED"
            elif low_completeness:
                bias_reason = f"LOW_COMPLETENESS_RATIO_{ratio:.2f}"

            return SamplingCompletenessMetrics(
                total_enqueued=self.total_enqueued,
                total_retained=max(0, self.total_enqueued - self.total_dropped),
                total_dropped=self.total_dropped,
                dropped_by_priority=dict(self.dropped_by_priority),
                completeness_ratio=ratio,
                sampling_bias_warning=bias_warning,
                bias_reason=bias_reason,
            )

    def clear(self) -> None:
        """Clear queue items and reset counters."""
        with self._lock:
            self._queue.clear()
            self._emergency_buffer.clear()
            self.total_enqueued = 0
            self.total_dropped = 0
            self.dropped_by_priority = {p: 0 for p in self.dropped_by_priority}
            self.recent_dropped.clear()


class ShadowEventBusAdapter:
    """Binds PriorityShadowQueue to the CanonicalEventBus as a non-blocking listener."""

    def __init__(self, queue: PriorityShadowQueue) -> None:
        self.queue = queue
        self._handle: Any = None

    def start(self) -> None:
        """Subscribe to all events on the global event bus."""
        from .event_bus import get_global_event_bus

        bus = get_global_event_bus()
        self._handle = bus.subscribe(self._on_event)

    def stop(self) -> None:
        """Unsubscribe from the event bus."""
        if self._handle:
            self._handle.unsubscribe()
            self._handle = None

    def _on_event(self, envelope: CanonicalEventEnvelope) -> None:
        """Receive published event and enqueue into shadow queue non-blockingly."""
        self.queue.enqueue(envelope)
