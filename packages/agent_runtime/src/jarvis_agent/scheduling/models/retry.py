"""Side-effect aware retry policies, decisions, and loop prevention fingerprints."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
from typing import Any

from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass


class RecoveryAction(str, Enum):
    """Authoritative action taken upon node execution failure."""

    RETRY = "RETRY"  # Re-dispatch same command with attempt_id + 1
    REPLAN = "REPLAN"  # Hand back to Track 3.1 replanner
    COMPENSATE = "COMPENSATE"  # Execute pre-authorized compensating node
    ESCALATE = "ESCALATE"  # Escalate to operator / user
    FAIL = "FAIL"  # Terminal failure without retry


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Policy governing retryability based on failure class and capability side-effect class."""

    max_retries: int = 3
    initial_delay_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 30.0
    jitter_factor: float = 0.1
    retryable_failure_classes: set[ExecutionFailureClass] = field(
        default_factory=lambda: {
            ExecutionFailureClass.TIMEOUT,
            ExecutionFailureClass.NETWORK_FAILURE,
            ExecutionFailureClass.EXECUTION_FAILURE,
            ExecutionFailureClass.OBSERVATION_FAILURE,
        }
    )

    def calculate_delay(self, attempt_id: int) -> float:
        """Compute exponential backoff delay for given attempt."""
        delay = self.initial_delay_seconds * (self.backoff_multiplier ** max(0, attempt_id - 1))
        return min(delay, self.max_delay_seconds)


@dataclass(frozen=True, slots=True)
class RetryDecision:
    """Deterministic decision on how to handle an execution failure."""

    action: RecoveryAction
    reason: str
    delay_seconds: float = 0.0
    next_attempt_id: int | None = None
    fingerprint: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action"] = self.action.value
        return d


def compute_recovery_fingerprint(
    task_id: str,
    node_id: str,
    failure_class: str,
    arguments_hash: str,
    plan_revision: int,
) -> str:
    """Compute SHA-256 fingerprint of failure context for 3-strike loop detection."""
    raw = f"{task_id}:{node_id}:{failure_class}:{arguments_hash}:{plan_revision}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


__all__ = [
    "RecoveryAction",
    "RetryDecision",
    "RetryPolicy",
    "compute_recovery_fingerprint",
]
