"""jarvis_learning.models.lifecycle — atomic model status state machine.

Enforces valid lifecycle transitions and records transition history:
candidate -> shadow | rejected
shadow -> promoted | rejected
promoted -> rolled_back | archived
rolled_back -> archived
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from ..experience import now_ms


class ModelStatus(StrEnum):
    """Lifecycle status states for models."""

    INSUFFICIENT_DATA = "insufficient_data"
    TRAINING_FAILED = "training_failed"
    EVALUATION_FAILED = "evaluation_failed"
    REJECTED = "rejected"
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"


class InvalidLifecycleTransitionError(ValueError):
    """Raised when an illegal status transition is attempted."""


@dataclass(frozen=True, slots=True)
class StatusTransition:
    """Record of a state transition for auditing."""

    from_status: ModelStatus
    to_status: ModelStatus
    actor: str
    reason: str
    timestamp: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_status": self.from_status.value,
            "to_status": self.to_status.value,
            "actor": self.actor,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StatusTransition:
        return cls(
            from_status=ModelStatus(d["from_status"]),
            to_status=ModelStatus(d["to_status"]),
            actor=d["actor"],
            reason=d["reason"],
            timestamp=int(d["timestamp"]),
        )


class ModelLifecycle:
    """State machine governing model promotion, deployment, and deprecation."""

    VALID_TRANSITIONS: dict[ModelStatus, set[ModelStatus]] = {
        ModelStatus.CANDIDATE: {ModelStatus.SHADOW, ModelStatus.REJECTED},
        ModelStatus.SHADOW: {ModelStatus.PROMOTED, ModelStatus.REJECTED},
        ModelStatus.PROMOTED: {ModelStatus.ROLLED_BACK, ModelStatus.ARCHIVED},
        ModelStatus.ROLLED_BACK: {ModelStatus.ARCHIVED},
        ModelStatus.REJECTED: {ModelStatus.ARCHIVED},
        ModelStatus.ARCHIVED: set(),
        ModelStatus.INSUFFICIENT_DATA: set(),
        ModelStatus.TRAINING_FAILED: set(),
        ModelStatus.EVALUATION_FAILED: set(),
    }

    @classmethod
    def can_transition(cls, current: ModelStatus, target: ModelStatus) -> bool:
        """Check whether a transition is allowed."""
        return target in cls.VALID_TRANSITIONS.get(current, set())

    @classmethod
    def transition(
        cls,
        current: ModelStatus,
        target: ModelStatus,
        *,
        actor: str,
        reason: str,
    ) -> StatusTransition:
        """Validate and execute state transition."""
        if not cls.can_transition(current, target):
            raise InvalidLifecycleTransitionError(
                f"Cannot transition model lifecycle from '{current.value}' to '{target.value}'"
            )
        return StatusTransition(
            from_status=current,
            to_status=target,
            actor=actor,
            reason=reason,
            timestamp=now_ms(),
        )
