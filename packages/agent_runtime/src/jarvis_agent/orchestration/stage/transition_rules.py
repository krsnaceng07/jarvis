"""Formal legal stage transition matrix and transition validation rules."""

from __future__ import annotations

from jarvis_agent.orchestration.models.stage import TaskStage


class IllegalStageTransitionError(ValueError):
    """Raised when an illegal transition between TaskStages is attempted."""


LEGAL_TRANSITIONS: dict[TaskStage, set[TaskStage]] = {
    TaskStage.IDLE: {
        TaskStage.EXPLORATION,
        TaskStage.PLANNING,
        TaskStage.EXECUTION,
    },
    TaskStage.EXPLORATION: {
        TaskStage.CLARIFICATION,
        TaskStage.PLANNING,
        TaskStage.CANCELLED,
    },
    TaskStage.CLARIFICATION: {
        TaskStage.PLANNING,
        TaskStage.EXPLORATION,
        TaskStage.CANCELLED,
    },
    TaskStage.PLANNING: {
        TaskStage.EXECUTION,
        TaskStage.WAITING_FOR_APPROVAL,
        TaskStage.CLARIFICATION,
        TaskStage.CANCELLED,
    },
    TaskStage.EXECUTION: {
        TaskStage.WAITING_FOR_TOOL,
        TaskStage.VERIFICATION,
        TaskStage.WAITING_FOR_APPROVAL,
        TaskStage.RECOVERY,
        TaskStage.PAUSED,
        TaskStage.CANCELLED,
        TaskStage.COMPLETED,
    },
    TaskStage.WAITING_FOR_TOOL: {
        TaskStage.VERIFICATION,
        TaskStage.EXECUTION,
        TaskStage.RECOVERY,
        TaskStage.CANCELLED,
    },
    TaskStage.WAITING_FOR_APPROVAL: {
        TaskStage.EXECUTION,
        TaskStage.PLANNING,
        TaskStage.CANCELLED,
    },
    TaskStage.WAITING_FOR_USER: {
        TaskStage.PLANNING,
        TaskStage.EXECUTION,
        TaskStage.CANCELLED,
    },
    TaskStage.VERIFICATION: {
        TaskStage.EXECUTION,
        TaskStage.RECOVERY,
        TaskStage.REVIEW,
        TaskStage.COMPLETED,
    },
    TaskStage.RECOVERY: {
        TaskStage.EXECUTION,
        TaskStage.PLANNING,
        TaskStage.FAILED,
        TaskStage.CANCELLED,
    },
    TaskStage.REVIEW: {
        TaskStage.COMPLETED,
        TaskStage.PLANNING,
    },
    TaskStage.PAUSED: {
        TaskStage.EXECUTION,
        TaskStage.CANCELLED,
    },
    TaskStage.COMPLETED: set(),
    TaskStage.FAILED: set(),
    TaskStage.CANCELLED: set(),
}


def is_transition_legal(from_stage: TaskStage, to_stage: TaskStage) -> bool:
    """Return True if the transition from from_stage to to_stage is permitted."""
    if from_stage == to_stage:
        return True  # Idempotent state assertion is legal
    allowed = LEGAL_TRANSITIONS.get(from_stage, set())
    return to_stage in allowed


def validate_transition(from_stage: TaskStage, to_stage: TaskStage) -> None:
    """Validate that transition is legal, raising IllegalStageTransitionError if not."""
    if not is_transition_legal(from_stage, to_stage):
        raise IllegalStageTransitionError(
            f"Illegal stage transition from {from_stage.value} to {to_stage.value}. "
            f"Allowed target stages: {sorted([s.value for s in LEGAL_TRANSITIONS.get(from_stage, set())])}"
        )


__all__ = [
    "LEGAL_TRANSITIONS",
    "IllegalStageTransitionError",
    "is_transition_legal",
    "validate_transition",
]
