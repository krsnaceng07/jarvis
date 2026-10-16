"""Ephemeral client view state projection and staleness disclosure for Track 3.5.

Enforces Invariant T35-03 & Invariant T35-17:
- ClientViewState is a disposable projection, never runtime authority.
- Distinguishes live reality from stale cached state during disconnect/reconnect.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ViewFreshness(str, Enum):
    """Authoritative freshness state of the local projection."""

    LIVE = "live"
    DEGRADED = "degraded"
    STALE = "stale"
    RECONNECTING = "reconnecting"
    OFFLINE = "offline"


class NodeExecutionState(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    VERIFIED = "VERIFIED"


class TaskExecutionState(str, Enum):
    SUBMITTED = "SUBMITTED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class NodeViewState:
    """Client projection of a plan node's state."""

    node_id: str
    goal: str = ""
    capability: str = ""
    status: str = "READY"
    title: str = ""
    attempt: int = 1
    requires_approval: bool = False
    approval_id: str | None = None
    observation: str | None = None
    verification_passed: bool | None = None
    error_message: str | None = None

    @property
    def state(self) -> NodeExecutionState:
        s = (self.status or "READY").upper()
        if self.requires_approval and not self.approval_id:
            return NodeExecutionState.WAITING_APPROVAL
        try:
            return NodeExecutionState(s)
        except ValueError:
            return NodeExecutionState.READY


@dataclass
class TaskViewState:
    """Client projection of an active or completed task."""

    task_id: str
    title: str = ""
    stage: str = "INTENT_DISCOVERY"
    status: str = "ACTIVE"
    plan_revision: int = 1
    nodes: dict[str, NodeViewState] = field(default_factory=dict)
    stdout_chunks: list[str] = field(default_factory=list)
    pending_approvals: dict[str, dict[str, Any]] = field(default_factory=dict)
    cancellation_requested: bool = False
    cancellation_reason: str | None = None
    last_event_time_utc: str = ""

    @property
    def state(self) -> TaskExecutionState:
        s = (self.status or "ACTIVE").upper()
        try:
            return TaskExecutionState(s)
        except ValueError:
            return TaskExecutionState.ACTIVE


@dataclass
class ClientViewState:
    """Master local projection container across subscribed tasks."""

    freshness: ViewFreshness = ViewFreshness.LIVE
    tasks: dict[str, TaskViewState] = field(default_factory=dict)
    active_task_id: str | None = None
    last_authoritative_event_utc: str = ""
    _listeners: list[Callable[[ClientViewState], None]] = field(default_factory=list, repr=False)

    def add_listener(self, listener: Callable[[ClientViewState], None]) -> None:
        """Register a callback for state changes."""
        self._listeners.append(listener)

    def _notify(self) -> None:
        for listener in self._listeners:
            try:
                listener(self)
            except Exception:
                pass

    def get_or_create_task(self, task_id: str, title: str = "") -> TaskViewState:
        if task_id not in self.tasks:
            self.tasks[task_id] = TaskViewState(
                task_id=task_id,
                title=title or f"Task {task_id}",
                stage="INTENT_DISCOVERY",
                status="ACTIVE",
            )
            self._notify()
        return self.tasks[task_id]

    def mark_degraded(self, reason: str = "") -> None:
        self.freshness = ViewFreshness.DEGRADED
        self._notify()

    def mark_stale(self, reason: str | ViewFreshness = ViewFreshness.STALE) -> None:
        """Mark projection as non-live during network interruptions."""
        if isinstance(reason, ViewFreshness):
            self.freshness = reason
        else:
            self.freshness = ViewFreshness.STALE
        self._notify()

    def mark_reconnecting(self, reason: str = "") -> None:
        self.freshness = ViewFreshness.RECONNECTING
        self._notify()

    def mark_offline(self, reason: str = "") -> None:
        self.freshness = ViewFreshness.OFFLINE
        self._notify()

    def mark_live(self) -> None:
        self.freshness = ViewFreshness.LIVE
        self._notify()

    def clear(self) -> None:
        """Self-healing discard on projection corruption."""
        self.tasks.clear()
        self.active_task_id = None
        self.freshness = ViewFreshness.DEGRADED
        self._notify()


__all__ = [
    "ViewFreshness",
    "NodeExecutionState",
    "TaskExecutionState",
    "NodeViewState",
    "TaskViewState",
    "ClientViewState",
]
