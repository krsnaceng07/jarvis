"""jarvis.agents.task.workflow_state_machine — 18-State Workflow State Machine.

Provides full parity with OpenClaw's lifecycle execution tracking,
structured progress events, and explicit stage transitions:

18 Discrete Lifecycle States:
1. IDLE - Ready for user requests.
2. UNDERSTANDING - Parsing raw input, voice transcripts, or multimodal commands.
3. CLASSIFYING_REQUEST - Categorizing intent (new task, continuation, modification, etc.).
4. RESOLVING_CONTEXT - Resolving pronouns, target windows, active files, temporal facts.
5. PLANNING - Decomposing complex goals into discrete sequential steps.
6. WAITING_FOR_CONFIRMATION - Awaiting user approval for high-risk or irreversible actions.
7. EXECUTING - Running a tool, script, or OS command.
8. OBSERVING - Inspecting stdout, exit codes, process lists, or UI trees.
9. VERIFYING - Performing physical OS ground-truth verification (file exists, volume readback, etc.).
10. CONTINUING - Progressing to the next step in an active multi-step ledger.
11. PAUSED - Temporarily paused by user command or background wait.
12. WAITING_FOR_USER - Blocked on user input, question clarification, or disambiguation.
13. RECOVERING - Autonomous error classification and self-healing argument repair.
14. PARTIALLY_COMPLETED - Some steps succeeded, but remaining steps require intervention.
15. COMPLETED - All steps finished and verified.
16. FAILED - Execution failed and recovery boundaries exhausted.
17. BLOCKED - Dependency or precondition missing on host system.
18. CANCELLED - Task cancelled by explicit user instruction.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


class WorkflowState(str, Enum):
    """18 discrete lifecycle states for task workflow tracking."""

    IDLE = "IDLE"
    UNDERSTANDING = "UNDERSTANDING"
    CLASSIFYING_REQUEST = "CLASSIFYING_REQUEST"
    RESOLVING_CONTEXT = "RESOLVING_CONTEXT"
    PLANNING = "PLANNING"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    VERIFYING = "VERIFYING"
    CONTINUING = "CONTINUING"
    PAUSED = "PAUSED"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    RECOVERING = "RECOVERING"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Event emitted whenever a workflow state transition or progress update occurs."""

    event_id: str
    task_id: Optional[str]
    previous_state: WorkflowState
    new_state: WorkflowState
    step_index: Optional[int]
    total_steps: Optional[int]
    message: str
    timestamp: float
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "task_id": self.task_id,
            "previous_state": self.previous_state.value,
            "new_state": self.new_state.value,
            "step_index": self.step_index,
            "total_steps": self.total_steps,
            "message": self.message,
            "timestamp": self.timestamp,
            "details": dict(self.details),
        }


# Permitted state transitions table for strict deterministic transitions
VALID_TRANSITIONS: dict[WorkflowState, frozenset[WorkflowState]] = {
    WorkflowState.IDLE: frozenset(
        {
            WorkflowState.UNDERSTANDING,
            WorkflowState.CLASSIFYING_REQUEST,
            WorkflowState.RESOLVING_CONTEXT,
        }
    ),
    WorkflowState.UNDERSTANDING: frozenset(
        {
            WorkflowState.CLASSIFYING_REQUEST,
            WorkflowState.WAITING_FOR_USER,
            WorkflowState.IDLE,
            WorkflowState.FAILED,
        }
    ),
    WorkflowState.CLASSIFYING_REQUEST: frozenset(
        {
            WorkflowState.RESOLVING_CONTEXT,
            WorkflowState.PLANNING,
            WorkflowState.EXECUTING,
            WorkflowState.CONTINUING,
            WorkflowState.PAUSED,
            WorkflowState.CANCELLED,
            WorkflowState.WAITING_FOR_USER,
            WorkflowState.IDLE,
        }
    ),
    WorkflowState.RESOLVING_CONTEXT: frozenset(
        {
            WorkflowState.PLANNING,
            WorkflowState.EXECUTING,
            WorkflowState.WAITING_FOR_CONFIRMATION,
            WorkflowState.WAITING_FOR_USER,
            WorkflowState.BLOCKED,
            WorkflowState.FAILED,
        }
    ),
    WorkflowState.PLANNING: frozenset(
        {
            WorkflowState.WAITING_FOR_CONFIRMATION,
            WorkflowState.EXECUTING,
            WorkflowState.WAITING_FOR_USER,
            WorkflowState.BLOCKED,
            WorkflowState.FAILED,
        }
    ),
    WorkflowState.WAITING_FOR_CONFIRMATION: frozenset(
        {
            WorkflowState.EXECUTING,
            WorkflowState.CANCELLED,
            WorkflowState.WAITING_FOR_USER,
            WorkflowState.IDLE,
        }
    ),
    WorkflowState.EXECUTING: frozenset(
        {
            WorkflowState.OBSERVING,
            WorkflowState.VERIFYING,
            WorkflowState.RECOVERING,
            WorkflowState.FAILED,
            WorkflowState.BLOCKED,
            WorkflowState.CANCELLED,
        }
    ),
    WorkflowState.OBSERVING: frozenset(
        {
            WorkflowState.VERIFYING,
            WorkflowState.RECOVERING,
            WorkflowState.EXECUTING,
            WorkflowState.FAILED,
        }
    ),
    WorkflowState.VERIFYING: frozenset(
        {
            WorkflowState.CONTINUING,
            WorkflowState.COMPLETED,
            WorkflowState.PARTIALLY_COMPLETED,
            WorkflowState.RECOVERING,
            WorkflowState.FAILED,
        }
    ),
    WorkflowState.CONTINUING: frozenset(
        {
            WorkflowState.RESOLVING_CONTEXT,
            WorkflowState.EXECUTING,
            WorkflowState.WAITING_FOR_CONFIRMATION,
            WorkflowState.COMPLETED,
            WorkflowState.PAUSED,
        }
    ),
    WorkflowState.PAUSED: frozenset(
        {
            WorkflowState.CONTINUING,
            WorkflowState.EXECUTING,
            WorkflowState.CANCELLED,
            WorkflowState.IDLE,
        }
    ),
    WorkflowState.WAITING_FOR_USER: frozenset(
        {
            WorkflowState.UNDERSTANDING,
            WorkflowState.CLASSIFYING_REQUEST,
            WorkflowState.RESOLVING_CONTEXT,
            WorkflowState.EXECUTING,
            WorkflowState.CANCELLED,
            WorkflowState.IDLE,
        }
    ),
    WorkflowState.RECOVERING: frozenset(
        {
            WorkflowState.EXECUTING,
            WorkflowState.VERIFYING,
            WorkflowState.PARTIALLY_COMPLETED,
            WorkflowState.FAILED,
            WorkflowState.BLOCKED,
        }
    ),
    WorkflowState.PARTIALLY_COMPLETED: frozenset(
        {
            WorkflowState.CONTINUING,
            WorkflowState.PLANNING,
            WorkflowState.WAITING_FOR_USER,
            WorkflowState.IDLE,
        }
    ),
    WorkflowState.COMPLETED: frozenset(
        {
            WorkflowState.IDLE,
            WorkflowState.UNDERSTANDING,
        }
    ),
    WorkflowState.FAILED: frozenset(
        {
            WorkflowState.IDLE,
            WorkflowState.UNDERSTANDING,
            WorkflowState.RECOVERING,
        }
    ),
    WorkflowState.BLOCKED: frozenset(
        {
            WorkflowState.IDLE,
            WorkflowState.UNDERSTANDING,
            WorkflowState.RESOLVING_CONTEXT,
            WorkflowState.WAITING_FOR_USER,
        }
    ),
    WorkflowState.CANCELLED: frozenset(
        {
            WorkflowState.IDLE,
            WorkflowState.UNDERSTANDING,
        }
    ),
}


class WorkflowStateMachine:
    """State machine maintaining execution lifecycle state and emitting progress events."""

    def __init__(self, initial_state: WorkflowState = WorkflowState.IDLE) -> None:
        self._current_state: WorkflowState = initial_state
        self._task_id: Optional[str] = None
        self._step_index: Optional[int] = None
        self._total_steps: Optional[int] = None
        self._listeners: list[Callable[[ProgressEvent], None]] = []
        self._event_history: list[ProgressEvent] = []
        self._state_entered_at: float = time.time()

    @property
    def current_state(self) -> WorkflowState:
        return self._current_state

    @property
    def task_id(self) -> Optional[str]:
        return self._task_id

    @property
    def event_history(self) -> list[ProgressEvent]:
        return list(self._event_history)

    def attach_task(
        self, task_id: str, step_index: Optional[int] = None, total_steps: Optional[int] = None
    ) -> None:
        """Attach an active task reference to the state machine."""
        self._task_id = task_id
        self._step_index = step_index
        self._total_steps = total_steps

    def detach_task(self) -> None:
        """Clear task reference and reset to IDLE."""
        self._task_id = None
        self._step_index = None
        self._total_steps = None
        if self._current_state != WorkflowState.IDLE:
            self.transition(WorkflowState.IDLE, message="Task detached; returning to IDLE.")

    def add_listener(self, listener: Callable[[ProgressEvent], None]) -> None:
        """Register a callback for progress events."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[ProgressEvent], None]) -> None:
        """Unregister a callback."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def can_transition(self, target_state: WorkflowState) -> bool:
        """Check whether transition from current state to target_state is permitted."""
        valid_next = VALID_TRANSITIONS.get(self._current_state, frozenset())
        return target_state in valid_next

    def transition(
        self,
        target_state: WorkflowState,
        message: str = "",
        details: Optional[dict[str, Any]] = None,
        force: bool = False,
    ) -> ProgressEvent:
        """Transition to a new state and emit a ProgressEvent.

        Args:
            target_state: Desired destination WorkflowState.
            message: Human-readable explanation of the transition.
            details: Contextual metadata (e.g. tool name, error reason).
            force: Bypass transition graph validation (e.g. for emergency reset).
        """
        if not force and not self.can_transition(target_state):
            raise ValueError(
                f"Invalid workflow transition: Cannot move from {self._current_state.value} to {target_state.value}."
            )

        prev_state = self._current_state
        now = time.time()
        self._current_state = target_state
        self._state_entered_at = now

        event = ProgressEvent(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            task_id=self._task_id,
            previous_state=prev_state,
            new_state=target_state,
            step_index=self._step_index,
            total_steps=self._total_steps,
            message=message or f"Transitioned from {prev_state.value} to {target_state.value}",
            timestamp=now,
            details=details or {},
        )

        self._event_history.append(event)
        if len(self._event_history) > 100:
            self._event_history = self._event_history[-100:]

        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

        return event

    def format_status_snapshot(self) -> dict[str, Any]:
        """Generate a complete structured status snapshot (OpenClaw task-status parity)."""
        duration = time.time() - self._state_entered_at
        return {
            "state": self._current_state.value,
            "task_id": self._task_id,
            "step_index": self._step_index,
            "total_steps": self._total_steps,
            "seconds_in_state": round(duration, 2),
            "recent_events": [e.to_dict() for e in self._event_history[-5:]],
        }
