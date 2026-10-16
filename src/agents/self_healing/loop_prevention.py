"""src.agents.self_healing.loop_prevention — Loop prevention and circuit breaking for recovery.

OpenClaw parity: mirrors completeToolLoopInterventionBatch and bounded attempt
supervisors to prevent infinite retry and repair thrashing.
"""

from __future__ import annotations

import collections
import threading
from typing import Any

from .failure_event import ErrorCategory

DEFAULT_MAX_TOOL_REPAIR_ATTEMPTS: int = 2
DEFAULT_MAX_TRANSIENT_RETRY_ATTEMPTS: int = 3
DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT: int = 1
DEFAULT_REASONING_ONLY_RETRY_LIMIT: int = 2
DEFAULT_MAX_TOTAL_RECOVERIES_PER_TASK: int = 10


class LoopPreventionEngine:
    """Tracks failure signatures and blocks infinite recovery cycles."""

    def __init__(
        self,
        max_tool_repairs: int = DEFAULT_MAX_TOOL_REPAIR_ATTEMPTS,
        max_transient_retries: int = DEFAULT_MAX_TRANSIENT_RETRY_ATTEMPTS,
        max_total_recoveries: int = DEFAULT_MAX_TOTAL_RECOVERIES_PER_TASK,
        max_empty_response_retries: int = DEFAULT_EMPTY_RESPONSE_RETRY_LIMIT,
        max_reasoning_only_retries: int = DEFAULT_REASONING_ONLY_RETRY_LIMIT,
    ) -> None:
        self.max_tool_repairs = max_tool_repairs
        self.max_transient_retries = max_transient_retries
        self.max_total_recoveries = max_total_recoveries
        self.max_empty_response_retries = max_empty_response_retries
        self.max_reasoning_only_retries = max_reasoning_only_retries

        self._lock = threading.Lock()
        self._signature_attempts: collections.defaultdict[str, int] = collections.defaultdict(int)
        self._signature_history: collections.defaultdict[str, list[dict[str, Any]]] = (
            collections.defaultdict(list)
        )
        self._total_recoveries: int = 0

    def get_max_attempts_for_category(self, category: ErrorCategory) -> int:
        """Return allowed attempt budget based on error category."""
        if category == ErrorCategory.EMPTY_RESPONSE:
            return self.max_empty_response_retries
        if category == ErrorCategory.REASONING_ONLY:
            return self.max_reasoning_only_retries
        if category in (
            ErrorCategory.NETWORK_TRANSIENT,
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.MODEL_OVERLOADED,
        ):
            return self.max_transient_retries
        return self.max_tool_repairs

    def can_attempt_recovery(
        self,
        signature: str,
        category: ErrorCategory,
    ) -> tuple[bool, str | None]:
        """Check whether recovery can proceed or if the circuit breaker must trip.

        Returns:
            (True, None) if recovery is permitted.
            (False, reason) if recovery is blocked due to threshold exhaustion.
        """
        with self._lock:
            if self._total_recoveries >= self.max_total_recoveries:
                return (
                    False,
                    f"Aggregate task recovery budget exceeded ({self._total_recoveries}/{self.max_total_recoveries} recoveries).",
                )

            current_attempts = self._signature_attempts[signature]
            max_allowed = self.get_max_attempts_for_category(category)

            if current_attempts >= max_allowed:
                return (
                    False,
                    f"Recovery circuit breaker tripped: failure signature '{signature}' "
                    f"has already reached the maximum allowed attempts ({current_attempts}/{max_allowed}). "
                    f"Further automatic recovery halted to prevent infinite loops.",
                )

            return True, None

    def record_attempt(
        self,
        signature: str,
        action: str,
        success: bool,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record an attempted recovery action."""
        with self._lock:
            self._signature_attempts[signature] += 1
            self._total_recoveries += 1
            self._signature_history[signature].append(
                {
                    "action": action,
                    "success": success,
                    "details": details or {},
                }
            )

    def get_signature_attempt_count(self, signature: str) -> int:
        """Get number of recovery attempts recorded for this signature."""
        with self._lock:
            return self._signature_attempts[signature]

    def reset(self) -> None:
        """Reset internal counters for a new task or session."""
        with self._lock:
            self._signature_attempts.clear()
            self._signature_history.clear()
            self._total_recoveries = 0


__all__ = [
    "DEFAULT_MAX_TOOL_REPAIR_ATTEMPTS",
    "DEFAULT_MAX_TOTAL_RECOVERIES_PER_TASK",
    "DEFAULT_MAX_TRANSIENT_RETRY_ATTEMPTS",
    "LoopPreventionEngine",
]
