"""jarvis.agents.steering_queue — in-memory steering queue and synthetic tool skip result generation.

OpenClaw parity: mirrors
``openclaw-main/src/agents/agent-steering-queue.ts`` and
``openclaw-main/src/auto-reply/reply/commands-steer.ts``.

Features:
- `SYNTHETIC_SKIPPED_TOOL_RESULT`: ``"Skipped due to queued user message."``
- `AgentSteeringQueue`: Session-scoped in-memory queue for steering prompts into active runs.
- `generate_synthetic_skipped_tool_result()`: Creates paired synthetic tool results for unstarted sequential tool calls.
- Stale lease timeout: 5 minutes (300,000 ms).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

SYNTHETIC_SKIPPED_TOOL_RESULT: str = "Skipped due to queued user message."
STALE_STEERING_LEASE_MS: int = 5 * 60 * 1000  # 5 minutes


@dataclass
class SteeringQueueItem:
    run_id: str
    message: str
    sender: str | None = None
    created_at: float = field(default_factory=time.time)
    leased_at: float | None = None
    lease_id: str | None = None


def generate_synthetic_skipped_tool_result(
    tool_call_id: str,
    tool_name: str,
) -> dict[str, Any]:
    """Generate paired synthetic error result for an unstarted tool call when steering is accepted.

    Mirrors OpenClaw synthetic tool skip generation.
    """
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "name": tool_name,
        "content": SYNTHETIC_SKIPPED_TOOL_RESULT,
        "error": True,
        "skipped_by_steering": True,
    }


class AgentSteeringQueue:
    """Session-scoped steering queue.

    Mirrors ``AgentSteeringQueue`` (``agent-steering-queue.ts``).
    """

    def __init__(self, session_key: str) -> None:
        self.session_key = session_key
        self._items: list[SteeringQueueItem] = []

    def enqueue(self, run_id: str, message: str, sender: str | None = None) -> SteeringQueueItem:
        """Enqueue a steering message."""
        item = SteeringQueueItem(
            run_id=run_id,
            message=message.strip(),
            sender=sender,
        )
        self._items.append(item)
        return item

    def peek(self) -> SteeringQueueItem | None:
        """Return the next unleased item without removing it."""
        now = time.time()
        for item in self._items:
            if item.leased_at is None:
                return item
            # Re-claim stale lease
            if (now - item.leased_at) * 1000.0 > STALE_STEERING_LEASE_MS:
                item.leased_at = None
                item.lease_id = None
                return item
        return None

    def lease_batch(self, lease_id: str, max_items: int = 20) -> list[SteeringQueueItem]:
        """Lease a batch of unleased items for injection."""
        now = time.time()
        leased: list[SteeringQueueItem] = []

        for item in self._items:
            if item.leased_at is None or (now - item.leased_at) * 1000.0 > STALE_STEERING_LEASE_MS:
                item.leased_at = now
                item.lease_id = lease_id
                leased.append(item)
                if len(leased) >= max_items:
                    break

        return leased

    def commit_lease(self, lease_id: str) -> None:
        """Commit (remove) leased items after successful injection."""
        self._items = [it for it in self._items if it.lease_id != lease_id]

    def rollback_lease(self, lease_id: str) -> None:
        """Rollback (un-lease) items if injection failed."""
        for item in self._items:
            if item.lease_id == lease_id:
                item.leased_at = None
                item.lease_id = None

    def clear(self) -> None:
        """Clear all items."""
        self._items.clear()

    def size(self) -> int:
        """Return number of pending items."""
        return len(self._items)


__all__ = [
    "STALE_STEERING_LEASE_MS",
    "SYNTHETIC_SKIPPED_TOOL_RESULT",
    "AgentSteeringQueue",
    "SteeringQueueItem",
    "generate_synthetic_skipped_tool_result",
]
