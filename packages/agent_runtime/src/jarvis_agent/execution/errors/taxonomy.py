"""Closed Error Taxonomy and Recovery Action Mapping for Track 3.2.

Classifies all execution, sandbox, admission, observation, and verification failures
into deterministic failure classes with explicit recovery action recommendations.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import enum
from typing import Any


class ExecutionFailureClass(enum.Enum):
    """Closed classification of execution layer failures."""

    INVALID_COMMAND = "INVALID_COMMAND"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    UNKNOWN_CAPABILITY = "UNKNOWN_CAPABILITY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    POLICY_DENIED = "POLICY_DENIED"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    SANDBOX_DENIED = "SANDBOX_DENIED"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    TIMEOUT = "TIMEOUT"
    CANCELLED = "CANCELLED"
    TOOL_UNAVAILABLE = "TOOL_UNAVAILABLE"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    HOST_FAILURE = "HOST_FAILURE"
    NETWORK_FAILURE = "NETWORK_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    OBSERVATION_FAILURE = "OBSERVATION_FAILURE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"
    STATE_DRIFT = "STATE_DRIFT"
    AMBIGUOUS_EXECUTION = "AMBIGUOUS_EXECUTION"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    STALE_COMMAND = "STALE_COMMAND"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ActionRecommendation(enum.Enum):
    """Recommended recovery action for orchestration to take following failure."""

    RETRY = "RETRY"
    REPLAN = "REPLAN"
    WAIT = "WAIT"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    REQUEST_USER = "REQUEST_USER"
    ESCALATE = "ESCALATE"
    FAIL = "FAIL"
    RECONCILE = "RECONCILE"


# Canonical mapping from failure class to default recovery action recommendation
FAILURE_TO_ACTION_MAP: dict[ExecutionFailureClass, ActionRecommendation] = {
    ExecutionFailureClass.INVALID_COMMAND: ActionRecommendation.FAIL,
    ExecutionFailureClass.INVALID_ARGUMENTS: ActionRecommendation.REPLAN,
    ExecutionFailureClass.UNKNOWN_CAPABILITY: ActionRecommendation.REPLAN,
    ExecutionFailureClass.PERMISSION_DENIED: ActionRecommendation.REQUEST_APPROVAL,
    ExecutionFailureClass.POLICY_DENIED: ActionRecommendation.REQUEST_USER,
    ExecutionFailureClass.APPROVAL_INVALID: ActionRecommendation.REQUEST_APPROVAL,
    ExecutionFailureClass.SANDBOX_DENIED: ActionRecommendation.FAIL,
    ExecutionFailureClass.RESOURCE_LIMIT: ActionRecommendation.REPLAN,
    ExecutionFailureClass.TIMEOUT: ActionRecommendation.RETRY,
    ExecutionFailureClass.CANCELLED: ActionRecommendation.FAIL,
    ExecutionFailureClass.TOOL_UNAVAILABLE: ActionRecommendation.REPLAN,
    ExecutionFailureClass.DEPENDENCY_FAILURE: ActionRecommendation.REPLAN,
    ExecutionFailureClass.HOST_FAILURE: ActionRecommendation.ESCALATE,
    ExecutionFailureClass.NETWORK_FAILURE: ActionRecommendation.RETRY,
    ExecutionFailureClass.EXECUTION_FAILURE: ActionRecommendation.RETRY,
    ExecutionFailureClass.OBSERVATION_FAILURE: ActionRecommendation.RETRY,
    ExecutionFailureClass.VERIFICATION_FAILURE: ActionRecommendation.REPLAN,
    ExecutionFailureClass.STATE_DRIFT: ActionRecommendation.REPLAN,
    ExecutionFailureClass.AMBIGUOUS_EXECUTION: ActionRecommendation.RECONCILE,
    ExecutionFailureClass.IDEMPOTENCY_CONFLICT: ActionRecommendation.FAIL,
    ExecutionFailureClass.STALE_COMMAND: ActionRecommendation.REPLAN,
    ExecutionFailureClass.INTERNAL_ERROR: ActionRecommendation.ESCALATE,
}


@dataclass(frozen=True, slots=True)
class ExecutionErrorDetail:
    """Structured detail describing an execution error."""

    failure_class: ExecutionFailureClass
    message: str
    recommended_action: ActionRecommendation
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Serialize error detail to dictionary."""
        d = asdict(self)
        d["failure_class"] = self.failure_class.value
        d["recommended_action"] = self.recommended_action.value
        return d

    @classmethod
    def create(
        cls,
        failure_class: ExecutionFailureClass,
        message: str,
        recommended_action: ActionRecommendation | None = None,
        details: dict[str, Any] | None = None,
    ) -> ExecutionErrorDetail:
        """Create an ExecutionErrorDetail with automatic action mapping fallback."""
        action = recommended_action or FAILURE_TO_ACTION_MAP.get(
            failure_class, ActionRecommendation.FAIL
        )
        return cls(
            failure_class=failure_class,
            message=message,
            recommended_action=action,
            details=details or {},
        )


__all__ = [
    "ActionRecommendation",
    "ExecutionErrorDetail",
    "ExecutionFailureClass",
    "FAILURE_TO_ACTION_MAP",
]
