"""jarvis_learning.training.job_lifecycle — 19-state training job lifecycle machine.

Guarantees unambiguous state progression, validates prerequisite transitions,
and logs all lifecycle events to a durable audit trail.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass, field

from .errors import StateTransitionError

logger = logging.getLogger(__name__)


class TrainingJobState(enum.StrEnum):
    """The 19 canonical states of an offline training job."""

    DRAFT = "DRAFT"
    VALIDATING = "VALIDATING"
    REJECTED = "REJECTED"
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSE_REQUESTED = "PAUSE_REQUESTED"
    CHECKPOINTING = "CHECKPOINTING"
    PAUSED = "PAUSED"
    RESUME_VALIDATING = "RESUME_VALIDATING"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    ABORTING = "ABORTING"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    TIMED_OUT = "TIMED_OUT"
    RESOURCE_EXCEEDED = "RESOURCE_EXCEEDED"
    UNRESPONSIVE = "UNRESPONSIVE"


# Valid state transitions mapping
VALID_TRANSITIONS: dict[TrainingJobState, set[TrainingJobState]] = {
    TrainingJobState.DRAFT: {TrainingJobState.VALIDATING, TrainingJobState.REJECTED},
    TrainingJobState.VALIDATING: {
        TrainingJobState.QUEUED,
        TrainingJobState.REJECTED,
        TrainingJobState.FAILED,
    },
    TrainingJobState.REJECTED: set(),  # Terminal
    TrainingJobState.QUEUED: {
        TrainingJobState.STARTING,
        TrainingJobState.CANCELLATION_REQUESTED,
        TrainingJobState.ABORTED,
    },
    TrainingJobState.STARTING: {
        TrainingJobState.RUNNING,
        TrainingJobState.FAILED,
        TrainingJobState.ABORTED,
        TrainingJobState.RESOURCE_EXCEEDED,
    },
    TrainingJobState.RUNNING: {
        TrainingJobState.PAUSE_REQUESTED,
        TrainingJobState.CHECKPOINTING,
        TrainingJobState.CANCELLATION_REQUESTED,
        TrainingJobState.COMPLETED,
        TrainingJobState.FAILED,
        TrainingJobState.ABORTED,
        TrainingJobState.TIMED_OUT,
        TrainingJobState.RESOURCE_EXCEEDED,
        TrainingJobState.UNRESPONSIVE,
    },
    TrainingJobState.PAUSE_REQUESTED: {
        TrainingJobState.CHECKPOINTING,
        TrainingJobState.PAUSED,
        TrainingJobState.FAILED,
        TrainingJobState.ABORTED,
    },
    TrainingJobState.CHECKPOINTING: {
        TrainingJobState.RUNNING,
        TrainingJobState.PAUSED,
        TrainingJobState.COMPLETED,
        TrainingJobState.FAILED,
    },
    TrainingJobState.PAUSED: {
        TrainingJobState.RESUME_VALIDATING,
        TrainingJobState.CANCELLATION_REQUESTED,
        TrainingJobState.ABORTED,
    },
    TrainingJobState.RESUME_VALIDATING: {
        TrainingJobState.RUNNING,
        TrainingJobState.FAILED,
        TrainingJobState.PAUSED,
    },
    TrainingJobState.CANCELLATION_REQUESTED: {
        TrainingJobState.ABORTING,
        TrainingJobState.ABORTED,
    },
    TrainingJobState.ABORTING: {TrainingJobState.ABORTED, TrainingJobState.FAILED},
    TrainingJobState.RECOVERING: {
        TrainingJobState.RUNNING,
        TrainingJobState.FAILED,
        TrainingJobState.ABORTED,
    },
    TrainingJobState.COMPLETED: set(),  # Terminal
    TrainingJobState.FAILED: {TrainingJobState.RECOVERING},  # Can attempt recovery
    TrainingJobState.ABORTED: set(),  # Terminal
    TrainingJobState.TIMED_OUT: set(),  # Terminal
    TrainingJobState.RESOURCE_EXCEEDED: set(),  # Terminal
    TrainingJobState.UNRESPONSIVE: {TrainingJobState.ABORTED, TrainingJobState.FAILED},
}


@dataclass(frozen=True, slots=True)
class StateTransitionRecord:
    """Audit record for a lifecycle transition."""

    job_id: str
    from_state: TrainingJobState
    to_state: TrainingJobState
    reason: str
    timestamp: float


@dataclass(slots=True)
class JobStateMachine:
    """Manages state transitions and history for a training job."""

    job_id: str
    current_state: TrainingJobState = TrainingJobState.DRAFT
    history: list[StateTransitionRecord] = field(default_factory=list)

    def transition_to(self, new_state: TrainingJobState, reason: str = "") -> None:
        """Attempt to transition to new_state; raises StateTransitionError if illegal."""
        allowed = VALID_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            logger.error(
                "Illegal transition for job='%s': %s -> %s (allowed: %s)",
                self.job_id,
                self.current_state.value,
                new_state.value,
                [s.value for s in allowed],
            )
            raise StateTransitionError(self.current_state.value, new_state.value)

        record = StateTransitionRecord(
            job_id=self.job_id,
            from_state=self.current_state,
            to_state=new_state,
            reason=reason,
            timestamp=time.time(),
        )
        self.history.append(record)
        old_state = self.current_state
        self.current_state = new_state
        logger.info(
            "Job '%s' state transition: %s -> %s (reason='%s')",
            self.job_id,
            old_state.value,
            new_state.value,
            reason,
        )

    def is_terminal(self) -> bool:
        """Check whether job has reached a terminal state."""
        return len(VALID_TRANSITIONS.get(self.current_state, set())) == 0

    def is_active(self) -> bool:
        """Check whether job is actively consuming resources or running."""
        return self.current_state in (
            TrainingJobState.STARTING,
            TrainingJobState.RUNNING,
            TrainingJobState.CHECKPOINTING,
            TrainingJobState.PAUSE_REQUESTED,
        )


class WorkerLifecycleState(enum.StrEnum):
    """The 13 canonical lifecycle states of a supervised child worker."""

    DISABLED = "DISABLED"
    STARTING = "STARTING"
    AUTHENTICATING = "AUTHENTICATING"
    HANDSHAKE_PENDING = "HANDSHAKE_PENDING"
    READY = "READY"
    BUSY = "BUSY"
    DRAINING = "DRAINING"
    UNRESPONSIVE = "UNRESPONSIVE"
    TERMINATING = "TERMINATING"
    TERMINATED = "TERMINATED"
    RESTART_BACKOFF = "RESTART_BACKOFF"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"


VALID_WORKER_TRANSITIONS: dict[WorkerLifecycleState, set[WorkerLifecycleState]] = {
    WorkerLifecycleState.DISABLED: {WorkerLifecycleState.STARTING},
    WorkerLifecycleState.STARTING: {
        WorkerLifecycleState.AUTHENTICATING,
        WorkerLifecycleState.TERMINATED,
        WorkerLifecycleState.FAILED,
    },
    WorkerLifecycleState.AUTHENTICATING: {
        WorkerLifecycleState.HANDSHAKE_PENDING,
        WorkerLifecycleState.TERMINATED,
        WorkerLifecycleState.FAILED,
    },
    WorkerLifecycleState.HANDSHAKE_PENDING: {
        WorkerLifecycleState.READY,
        WorkerLifecycleState.UNRESPONSIVE,
        WorkerLifecycleState.TERMINATED,
        WorkerLifecycleState.FAILED,
    },
    WorkerLifecycleState.READY: {
        WorkerLifecycleState.BUSY,
        WorkerLifecycleState.DRAINING,
        WorkerLifecycleState.UNRESPONSIVE,
        WorkerLifecycleState.TERMINATING,
        WorkerLifecycleState.TERMINATED,
    },
    WorkerLifecycleState.BUSY: {
        WorkerLifecycleState.READY,
        WorkerLifecycleState.DRAINING,
        WorkerLifecycleState.UNRESPONSIVE,
        WorkerLifecycleState.TERMINATING,
        WorkerLifecycleState.TERMINATED,
    },
    WorkerLifecycleState.DRAINING: {
        WorkerLifecycleState.TERMINATING,
        WorkerLifecycleState.TERMINATED,
    },
    WorkerLifecycleState.UNRESPONSIVE: {
        WorkerLifecycleState.TERMINATING,
        WorkerLifecycleState.TERMINATED,
        WorkerLifecycleState.FAILED,
    },
    WorkerLifecycleState.TERMINATING: {
        WorkerLifecycleState.TERMINATED,
        WorkerLifecycleState.FAILED,
    },
    WorkerLifecycleState.TERMINATED: {
        WorkerLifecycleState.RESTART_BACKOFF,
        WorkerLifecycleState.QUARANTINED,
        WorkerLifecycleState.DISABLED,
    },
    WorkerLifecycleState.RESTART_BACKOFF: {
        WorkerLifecycleState.STARTING,
        WorkerLifecycleState.QUARANTINED,
        WorkerLifecycleState.DISABLED,
    },
    WorkerLifecycleState.QUARANTINED: {
        WorkerLifecycleState.DISABLED,
        WorkerLifecycleState.STARTING,  # Only on manual operator re-enable
    },
    WorkerLifecycleState.FAILED: {
        WorkerLifecycleState.RESTART_BACKOFF,
        WorkerLifecycleState.QUARANTINED,
        WorkerLifecycleState.DISABLED,
    },
}


@dataclass(slots=True)
class WorkerStateMachine:
    """Manages worker lifecycle transitions and enforces crash budget (INV-P9-SUP-001)."""

    worker_id: str
    current_state: WorkerLifecycleState = WorkerLifecycleState.DISABLED
    crash_window_seconds: float = 60.0
    max_crashes_per_window: int = 3
    crash_timestamps: list[float] = field(default_factory=list)

    def transition_to(self, new_state: WorkerLifecycleState, reason: str = "") -> None:
        """Transition worker state; raises StateTransitionError if invalid."""
        allowed = VALID_WORKER_TRANSITIONS.get(self.current_state, set())
        if new_state not in allowed:
            logger.error(
                "Illegal worker transition for '%s': %s -> %s (allowed: %s)",
                self.worker_id,
                self.current_state.value,
                new_state.value,
                [s.value for s in allowed],
            )
            raise StateTransitionError(self.current_state.value, new_state.value)

        old_state = self.current_state
        self.current_state = new_state
        logger.info(
            "Worker '%s' transition: %s -> %s (reason='%s')",
            self.worker_id,
            old_state.value,
            new_state.value,
            reason,
        )

    def record_crash(self) -> bool:
        """Record a crash event using monotonic time. Returns True if worker is QUARANTINED."""
        now = time.monotonic()
        # Prune crashes older than window
        self.crash_timestamps = [
            t for t in self.crash_timestamps if now - t <= self.crash_window_seconds
        ]
        self.crash_timestamps.append(now)

        if len(self.crash_timestamps) >= self.max_crashes_per_window:
            logger.critical(
                "CRASH_BUDGET_EXCEEDED: Worker '%s' crashed %d times in %.1fs -> QUARANTINED",
                self.worker_id,
                len(self.crash_timestamps),
                self.crash_window_seconds,
            )
            try:
                self.transition_to(WorkerLifecycleState.QUARANTINED, "Crash budget exceeded")
            except Exception:
                self.current_state = WorkerLifecycleState.QUARANTINED
            return True
        return False

    def is_quarantined(self) -> bool:
        return self.current_state == WorkerLifecycleState.QUARANTINED

    def reset_quarantine(self) -> None:
        """Manual operator reset of quarantined state."""
        self.crash_timestamps.clear()
        self.current_state = WorkerLifecycleState.DISABLED
        logger.info("Worker '%s' quarantine cleared by operator", self.worker_id)
