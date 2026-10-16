"""Authoritative 12-state node lifecycle machine and task aggregate states for Track 3.3.

Defines:
1. SchedulerNodeState: The formal 12-state node lifecycle.
2. TaskAggregateState: Authoritative rollup of overall task progress.
3. NodeStateTransition: Structured audit record of valid state transitions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from enum import Enum
from typing import Any


class SchedulerNodeState(str, Enum):
    """Authoritative 12-state lifecycle for discrete nodes in a PlanDAG."""

    PENDING = "PENDING"
    BLOCKED = "BLOCKED"
    ELIGIBLE = "ELIGIBLE"
    LEASED = "LEASED"
    DISPATCH_REQUESTED = "DISPATCH_REQUESTED"
    RUNNING = "RUNNING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    CANCELLATION_FAILED = "CANCELLATION_FAILED"

    @property
    def is_terminal(self) -> bool:
        """True if the node has terminated and cannot proceed without replanning/retry."""
        return self in (
            SchedulerNodeState.VERIFIED,
            SchedulerNodeState.FAILED,
            SchedulerNodeState.CANCELLED,
            SchedulerNodeState.AMBIGUOUS,
        )

    @property
    def is_in_flight(self) -> bool:
        """True if the node currently holds resources or active dispatch."""
        return self in (
            SchedulerNodeState.LEASED,
            SchedulerNodeState.DISPATCH_REQUESTED,
            SchedulerNodeState.RUNNING,
            SchedulerNodeState.OBSERVING,
            SchedulerNodeState.VERIFYING,
            SchedulerNodeState.CANCEL_REQUESTED,
        )

    @property
    def is_cancellable(self) -> bool:
        """True if the node can receive a cancellation request."""
        return not self.is_terminal and self != SchedulerNodeState.CANCEL_REQUESTED


VALID_NODE_TRANSITIONS: dict[SchedulerNodeState, set[SchedulerNodeState]] = {
    SchedulerNodeState.PENDING: {
        SchedulerNodeState.BLOCKED,
        SchedulerNodeState.ELIGIBLE,
        SchedulerNodeState.CANCEL_REQUESTED,
        SchedulerNodeState.CANCELLED,
    },
    SchedulerNodeState.BLOCKED: {
        SchedulerNodeState.ELIGIBLE,
        SchedulerNodeState.CANCEL_REQUESTED,
        SchedulerNodeState.CANCELLED,
    },
    SchedulerNodeState.ELIGIBLE: {
        SchedulerNodeState.LEASED,
        SchedulerNodeState.BLOCKED,
        SchedulerNodeState.CANCEL_REQUESTED,
        SchedulerNodeState.CANCELLED,
    },
    SchedulerNodeState.LEASED: {
        SchedulerNodeState.DISPATCH_REQUESTED,
        SchedulerNodeState.ELIGIBLE,
        SchedulerNodeState.CANCEL_REQUESTED,
    },
    SchedulerNodeState.DISPATCH_REQUESTED: {
        SchedulerNodeState.RUNNING,
        SchedulerNodeState.FAILED,
        SchedulerNodeState.CANCEL_REQUESTED,
        SchedulerNodeState.AMBIGUOUS,
    },
    SchedulerNodeState.RUNNING: {
        SchedulerNodeState.OBSERVING,
        SchedulerNodeState.FAILED,
        SchedulerNodeState.CANCEL_REQUESTED,
        SchedulerNodeState.AMBIGUOUS,
    },
    SchedulerNodeState.OBSERVING: {
        SchedulerNodeState.VERIFYING,
        SchedulerNodeState.FAILED,
        SchedulerNodeState.CANCEL_REQUESTED,
        SchedulerNodeState.AMBIGUOUS,
    },
    SchedulerNodeState.VERIFYING: {
        SchedulerNodeState.VERIFIED,
        SchedulerNodeState.FAILED,
        SchedulerNodeState.AMBIGUOUS,
    },
    SchedulerNodeState.CANCEL_REQUESTED: {
        SchedulerNodeState.CANCELLED,
        SchedulerNodeState.CANCELLATION_FAILED,
        SchedulerNodeState.AMBIGUOUS,
    },
    SchedulerNodeState.CANCELLATION_FAILED: {
        SchedulerNodeState.RUNNING,
        SchedulerNodeState.FAILED,
        SchedulerNodeState.AMBIGUOUS,
    },
    SchedulerNodeState.VERIFIED: set(),
    SchedulerNodeState.FAILED: {
        SchedulerNodeState.ELIGIBLE,
    },
    SchedulerNodeState.AMBIGUOUS: {
        SchedulerNodeState.VERIFIED,
        SchedulerNodeState.FAILED,
        SchedulerNodeState.ELIGIBLE,
    },
    SchedulerNodeState.CANCELLED: set(),
}


class TaskAggregateState(str, Enum):
    """Aggregate progress state for an overall orchestration task."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    AMBIGUOUS = "AMBIGUOUS"
    BLOCKED = "BLOCKED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class NodeStateTransition:
    """Immutable audit record of a node transitioning between states."""

    node_id: str
    task_id: str
    from_state: SchedulerNodeState
    to_state: SchedulerNodeState
    timestamp_utc: str
    reason: str
    worker_id: str | None = None
    attempt_id: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["from_state"] = self.from_state.value
        d["to_state"] = self.to_state.value
        return d

    @classmethod
    def create(
        cls,
        node_id: str,
        task_id: str,
        from_state: SchedulerNodeState,
        to_state: SchedulerNodeState,
        reason: str,
        worker_id: str | None = None,
        attempt_id: int = 1,
        timestamp_utc: str | None = None,
    ) -> NodeStateTransition:
        valid_targets = VALID_NODE_TRANSITIONS.get(from_state, set())
        if to_state not in valid_targets:
            raise ValueError(
                f"Invalid node state transition: cannot transition from {from_state.value} to {to_state.value}"
            )
        now_str = timestamp_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()
        return cls(
            node_id=node_id,
            task_id=task_id,
            from_state=from_state,
            to_state=to_state,
            timestamp_utc=now_str,
            reason=reason,
            worker_id=worker_id,
            attempt_id=attempt_id,
        )


__all__ = [
    "SchedulerNodeState",
    "TaskAggregateState",
    "NodeStateTransition",
    "VALID_NODE_TRANSITIONS",
]
