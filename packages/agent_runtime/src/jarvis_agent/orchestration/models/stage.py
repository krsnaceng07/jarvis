"""Fourteen-stage lifecycle state enum and metadata for JARVIS tasks."""

from __future__ import annotations

from enum import Enum


class TaskStage(str, Enum):
    """Explicit lifecycle stages for an autonomous task."""

    IDLE = "IDLE"
    EXPLORATION = "EXPLORATION"
    CLARIFICATION = "CLARIFICATION"
    PLANNING = "PLANNING"
    EXECUTION = "EXECUTION"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    WAITING_FOR_USER = "WAITING_FOR_USER"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    VERIFICATION = "VERIFICATION"
    RECOVERY = "RECOVERY"
    REVIEW = "REVIEW"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    @property
    def is_terminal(self) -> bool:
        """True if the stage represents a terminal task state."""
        return self in (
            TaskStage.COMPLETED,
            TaskStage.FAILED,
            TaskStage.CANCELLED,
        )

    @property
    def is_waiting(self) -> bool:
        """True if the stage represents an external pause or wait condition."""
        return self in (
            TaskStage.WAITING_FOR_TOOL,
            TaskStage.WAITING_FOR_USER,
            TaskStage.WAITING_FOR_APPROVAL,
            TaskStage.PAUSED,
        )

    @property
    def is_active(self) -> bool:
        """True if the task is actively in flight."""
        return not self.is_terminal and self != TaskStage.IDLE


__all__ = ["TaskStage"]
