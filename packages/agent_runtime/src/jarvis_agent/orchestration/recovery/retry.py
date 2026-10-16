"""Retry management and failure classification with exponential backoff and jitter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random


class FailureClass(str, Enum):
    """Categorical classification of execution failure causes."""

    TRANSIENT = "TRANSIENT"  # Network hiccup, temporary lock -> Retryable
    TIMEOUT = "TIMEOUT"  # Operation took too long -> Retryable
    PERMISSION_DENIED = "PERMISSION"  # OS or API access denied -> Escalation required
    VALIDATION_FAILED = "VALIDATION"  # Verification assertion failed -> Replanning required
    CORRUPT_STATE = "CORRUPT_STATE"  # State inconsistency -> Crash recovery required
    FATAL = "FATAL"  # Unrecoverable error -> Task failure


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Configuration for retry backoff and attempt limits."""

    initial_backoff_seconds: float = 1.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0
    max_retries: int = 3
    jitter: bool = True


class RetryManager:
    """Manages retry evaluations and exponential backoff calculations."""

    def __init__(self, policy: RetryPolicy | None = None) -> None:
        self._policy = policy or RetryPolicy()

    def is_retryable(self, failure_class: FailureClass) -> bool:
        """Transient and timeout errors are retryable; permission and fatal errors are not."""
        return failure_class in (FailureClass.TRANSIENT, FailureClass.TIMEOUT)

    def evaluate_retry(
        self,
        failure_class: FailureClass,
        current_attempt: int,
    ) -> tuple[bool, float]:
        """Compute whether to retry and the backoff delay in seconds."""
        if not self.is_retryable(failure_class):
            return False, 0.0

        if current_attempt >= self._policy.max_retries:
            return False, 0.0

        backoff = min(
            self._policy.max_backoff_seconds,
            self._policy.initial_backoff_seconds
            * (self._policy.backoff_multiplier ** (current_attempt - 1)),
        )

        if self._policy.jitter:
            backoff = backoff * (0.8 + 0.4 * random.random())

        return True, round(backoff, 2)


__all__ = ["FailureClass", "RetryManager", "RetryPolicy"]
