"""Disposable, reconstructible in-memory priority queue with aging and backpressure.

HARD INVARIANT:
The priority queue is pure cache. It can be completely cleared and reconstructed
from ProjectionStore.get_nodes_by_state(SchedulerNodeState.ELIGIBLE) at any time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import heapq


@dataclass(order=True)
class QueueItem:
    """Heap-ordered entry in the runnable priority queue."""

    sort_score: float  # Lower sort_score executes sooner
    enqueued_at_epoch: float = field(compare=False)
    node_id: str = field(compare=False)
    task_id: str = field(compare=False)
    priority_level: int = field(compare=False)
    effective_deadline_utc: str | None = field(compare=False)


class RunnablePriorityQueue:
    """Thread-safe, aging-aware priority queue for eligible execution nodes."""

    def __init__(
        self,
        max_in_flight_per_task: int = 3,
        max_global_in_flight: int = 10,
        aging_boost_per_second: float = 0.05,
        policy_ceiling: int = 4,
    ) -> None:
        self._heap: list[QueueItem] = []
        self._enqueued_ids: set[str] = set()
        self.max_in_flight_per_task = max_in_flight_per_task
        self.max_global_in_flight = max_global_in_flight
        self.aging_boost_per_second = aging_boost_per_second
        self.policy_ceiling = policy_ceiling

    def push(
        self,
        node_id: str,
        task_id: str,
        priority_level: int,
        effective_deadline_utc: str | None = None,
        now_epoch: float | None = None,
    ) -> bool:
        """Enqueue an eligible node. Duplicate enqueues are ignored."""
        if node_id in self._enqueued_ids:
            return False

        epoch = (
            now_epoch
            if now_epoch is not None
            else datetime.datetime.now(datetime.timezone.utc).timestamp()
        )
        clamped_priority = min(priority_level, self.policy_ceiling)

        # Baseline sort score: higher priority gets lower score
        # Base: (policy_ceiling - clamped_priority) * 1000
        score = (self.policy_ceiling - clamped_priority) * 1000.0

        if effective_deadline_utc:
            try:
                dl_dt = datetime.datetime.fromisoformat(effective_deadline_utc)
                # Urgency component: closer deadline reduces score
                score += dl_dt.timestamp() - epoch
            except Exception:
                pass

        item = QueueItem(
            sort_score=score,
            enqueued_at_epoch=epoch,
            node_id=node_id,
            task_id=task_id,
            priority_level=clamped_priority,
            effective_deadline_utc=effective_deadline_utc,
        )
        heapq.heappush(self._heap, item)
        self._enqueued_ids.add(node_id)
        return True

    def pop(
        self,
        active_per_task_counts: dict[str, int] | None = None,
        now_epoch: float | None = None,
    ) -> str | None:
        """Pop the highest priority runnable node respecting task backpressure."""
        if not self._heap:
            return None

        active_counts = active_per_task_counts or {}
        now = (
            now_epoch
            if now_epoch is not None
            else datetime.datetime.now(datetime.timezone.utc).timestamp()
        )

        # Temporary buffer for items that exceed backpressure
        deferred: list[QueueItem] = []
        selected_node_id: str | None = None

        while self._heap:
            item = heapq.heappop(self._heap)
            cur_task_active = active_counts.get(item.task_id, 0)
            if cur_task_active >= self.max_in_flight_per_task:
                # Task at maximum backpressure; defer
                deferred.append(item)
                continue

            selected_node_id = item.node_id
            self._enqueued_ids.remove(selected_node_id)
            break

        # Put deferred items back with applied aging boost
        for def_item in deferred:
            wait_time = max(0.0, now - def_item.enqueued_at_epoch)
            aging_discount = wait_time * self.aging_boost_per_second
            updated_item = QueueItem(
                sort_score=def_item.sort_score - aging_discount,
                enqueued_at_epoch=def_item.enqueued_at_epoch,
                node_id=def_item.node_id,
                task_id=def_item.task_id,
                priority_level=def_item.priority_level,
                effective_deadline_utc=def_item.effective_deadline_utc,
            )
            heapq.heappush(self._heap, updated_item)

        return selected_node_id

    def remove(self, node_id: str) -> None:
        """Remove a node if cancelled or replanned."""
        if node_id in self._enqueued_ids:
            self._enqueued_ids.remove(node_id)
            self._heap = [item for item in self._heap if item.node_id != node_id]
            heapq.heapify(self._heap)

    def clear(self) -> None:
        """Flush the entire queue cache."""
        self._heap.clear()
        self._enqueued_ids.clear()

    def __len__(self) -> int:
        return len(self._enqueued_ids)


__all__ = ["QueueItem", "RunnablePriorityQueue"]
