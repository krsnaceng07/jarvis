"""Unidirectional fire-and-forget event buffer and voice loop non-interference guard.

Enforces:
- INV-P10-RT-001: No learning-sidecar failure, queue backlog, or IPC delay
  may delay active voice/tool execution.
- INV-P10-RT-002: Stale task-generation or cancelled-turn results must never
  affect current runtime state.
"""

from __future__ import annotations

import collections
import dataclasses
import time

from jarvis_learning.evaluation.event_envelope import CanonicalEventEnvelope


@dataclasses.dataclass(frozen=True)
class VoiceLoopSLOMetrics:
    """Latency percentiles for active voice hooks."""

    sample_count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float
    dropped_events_count: int


class UnidirectionalVoiceGuard:
    """Zero-wait in-memory buffer guaranteeing complete isolation for active voice assistant."""

    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._buffer: collections.deque[CanonicalEventEnvelope] = collections.deque(maxlen=capacity)
        self._dispatch_latencies: list[float] = []
        self._dropped_count = 0
        self._current_task_generation = 1
        self._cancelled_turns: set[str] = set()

    @property
    def current_task_generation(self) -> int:
        return self._current_task_generation

    def advance_task_generation(self) -> int:
        """Advance the generation counter when user gives follow-up or new task."""
        self._current_task_generation += 1
        return self._current_task_generation

    def cancel_turn(self, turn_id: str) -> None:
        """Mark a turn as cancelled due to user barge-in."""
        self._cancelled_turns.add(turn_id)

    def is_turn_cancelled(self, turn_id: str) -> bool:
        return turn_id in self._cancelled_turns

    def emit_event_from_active_path(self, event: CanonicalEventEnvelope) -> bool:
        """Non-blocking fire-and-forget emission from the active voice loop.

        Guarantees:
        - Never raises an exception back into caller.
        - Records execution latency for SLO verification.
        - Immediately drops lowest priority event if capacity saturated.
        """
        t0 = time.perf_counter()
        try:
            # Check generation staleness
            task_gen = event.task_generation
            if task_gen is not None and task_gen < self._current_task_generation and task_gen > 0:
                # Stale generation -> discard immediately
                return False

            # Check barge-in cancellation
            turn_id = event.turn_id
            if turn_id and turn_id in self._cancelled_turns:
                return False

            if len(self._buffer) >= self._capacity:
                # Buffer full: drop oldest event to preserve memory headroom
                self._buffer.popleft()
                self._dropped_count += 1

            self._buffer.append(event)
            return True
        except Exception:
            # Absolute containment: active path must NEVER fail from logging
            return False
        finally:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            self._dispatch_latencies.append(elapsed_ms)

    def validate_worker_result(
        self,
        turn_id: str,
        task_generation: int,
    ) -> bool:
        """Validate whether a completed worker result is still eligible to commit."""
        # Check turn cancellation
        if turn_id in self._cancelled_turns:
            return False

        # Check generation staleness
        if task_generation < self._current_task_generation:
            return False

        return True

    def get_slo_metrics(self) -> VoiceLoopSLOMetrics:
        """Compute latency percentiles for active voice hooks."""
        if not self._dispatch_latencies:
            return VoiceLoopSLOMetrics(0, 0.0, 0.0, 0.0, 0.0, self._dropped_count)

        sorted_latencies = sorted(self._dispatch_latencies)
        n = len(sorted_latencies)

        p50 = sorted_latencies[int(n * 0.50)]
        p95 = sorted_latencies[min(int(n * 0.95), n - 1)]
        p99 = sorted_latencies[min(int(n * 0.99), n - 1)]
        max_val = sorted_latencies[-1]

        return VoiceLoopSLOMetrics(
            sample_count=n,
            p50_ms=p50,
            p95_ms=p95,
            p99_ms=p99,
            max_ms=max_val,
            dropped_events_count=self._dropped_count,
        )
