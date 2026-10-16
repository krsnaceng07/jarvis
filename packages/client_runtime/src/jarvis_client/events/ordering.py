"""Sequence ordering and continuity guards for Track 3.5.

Enforces:
1. Monotonic connection_seq validation per physical socket.
2. Global sequence tracking.
3. Per-task aggregate_version monotonicity.
4. Selective subscription tolerance (missing global_seq is normal for filtered views).
"""

from __future__ import annotations

from jarvis_client.errors import ClientErrorCode, SequenceGapError
from jarvis_client.events.decoder import DecodedEvent


class SequenceOrderingGuard:
    """Validates transport continuity and aggregate consistency."""

    def __init__(self, is_global_subscription: bool = False) -> None:
        self.is_global_subscription = is_global_subscription
        self._expected_connection_seq: int = 1
        self._last_global_seq: int = 0
        self._task_aggregate_versions: dict[str, int] = {}
        self._seen_event_ids: set[str] = set()

    @property
    def last_global_seq(self) -> int:
        return self._last_global_seq

    def reset_connection(self) -> None:
        """Reset socket-scoped transport counter on new WebSocket connection."""
        self._expected_connection_seq = 1

    def process_event(self, event: DecodedEvent) -> bool:
        """Verify event ordering.

        Returns True if event is valid and accepted; False if duplicate.
        Raises JarvisClientException on sequence corruption.
        """
        # Deduplication
        if event.event_id in self._seen_event_ids:
            return False
        self._seen_event_ids.add(event.event_id)

        # 1. Transport sequence check (per-socket)
        if event.connection_seq > 0:
            if event.connection_seq < self._expected_connection_seq:
                # Stale or duplicate transport frame
                return False
            if event.connection_seq > self._expected_connection_seq:
                raise SequenceGapError(
                    code=ClientErrorCode.CONNECTION_LOST,
                    message=f"Sequence gap: expected {self._expected_connection_seq}, got {event.connection_seq}",
                )
            self._expected_connection_seq = event.connection_seq + 1

        # 2. Global sequence check
        if event.global_seq > 0:
            if self.is_global_subscription and self._last_global_seq > 0:
                # If subscribed to whole journal, global_seq should be contiguous
                if event.global_seq > self._last_global_seq + 1:
                    pass  # Advisory in client, or gap trigger
            self._last_global_seq = max(self._last_global_seq, event.global_seq)

        # 3. Aggregate version monotonicity (per-task)
        task_id = event.payload.get("taskId") or event.payload.get("task_id")
        if task_id and event.aggregate_version > 0:
            tid_str = str(task_id)
            current_ver = self._task_aggregate_versions.get(tid_str, 0)
            if event.aggregate_version < current_ver:
                # Stale aggregate state received out of order
                return False
            self._task_aggregate_versions[tid_str] = event.aggregate_version

        return True

    check_and_advance = process_event


__all__ = ["SequenceOrderingGuard"]
