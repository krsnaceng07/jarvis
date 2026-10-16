"""jarvis_learning.routing.health — runtime statistical health and classified rollback.

Monitors live executions over a sliding window. Distinguishes model-caused
errors from external environmental outages (e.g. network disconnects, OS locks),
preventing false rollbacks.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExecutionHealthRecord:
    """Classified outcome of an active tool execution."""

    turn_id: str
    tool_name: str
    success: bool
    failure_cause: (
        str  # "none", "model_caused", "environment_caused", "user_input_caused", "external_service"
    )
    is_critical_safety_failure: bool
    is_false_claim: bool


@dataclass(frozen=True, slots=True)
class HealthDecision:
    """Evaluation of model health over the current sliding window."""

    is_healthy: bool
    rollback_required: bool
    trigger_reason: str
    model_caused_error_rate: float
    total_window_size: int
    consecutive_model_failures: int


class RuntimeHealthMonitor:
    """Monitors live execution health using sliding-window error classification."""

    def __init__(
        self,
        window_size: int = 30,
        max_consecutive_model_failures: int = 3,
        max_model_error_rate: float = 0.10,  # 10% maximum model-caused error rate
    ) -> None:
        self.window_size = window_size
        self.max_consecutive = max_consecutive_model_failures
        self.max_error_rate = max_model_error_rate
        self._history: deque[ExecutionHealthRecord] = deque(maxlen=window_size)

    def record_execution(
        self,
        *,
        turn_id: str,
        tool_name: str,
        success: bool,
        error_message: str = "",
        verification_status: str = "",
        is_critical_safety_failure: bool = False,
    ) -> HealthDecision:
        """Classify execution outcome and update sliding window health."""
        is_false_claim = verification_status == "false_claim"
        if not success:
            lower_err = error_message.lower()
            if "network" in lower_err or "connection" in lower_err or "timeout" in lower_err:
                cause = "external_service"
            elif "permission" in lower_err or "access denied" in lower_err:
                cause = "environment_caused"
            elif "syntax" in lower_err or "invalid input" in lower_err:
                cause = "user_input_caused"
            else:
                cause = "model_caused"
        else:
            cause = "none"

        record = ExecutionHealthRecord(
            turn_id=turn_id,
            tool_name=tool_name,
            success=success,
            failure_cause=cause,
            is_critical_safety_failure=is_critical_safety_failure,
            is_false_claim=is_false_claim,
        )
        self._history.append(record)
        return self.evaluate_health()

    def evaluate_health(self) -> HealthDecision:
        """Examine current sliding window for rollback triggers."""
        if not self._history:
            return HealthDecision(
                is_healthy=True,
                rollback_required=False,
                trigger_reason="No execution history",
                model_caused_error_rate=0.0,
                total_window_size=0,
                consecutive_model_failures=0,
            )

        # 1. Trigger: Single critical safety violation or false claim
        for r in self._history:
            if r.is_critical_safety_failure:
                return HealthDecision(
                    is_healthy=False,
                    rollback_required=True,
                    trigger_reason=f"Critical safety violation detected in turn {r.turn_id}",
                    model_caused_error_rate=1.0,
                    total_window_size=len(self._history),
                    consecutive_model_failures=1,
                )
            if r.is_false_claim:
                return HealthDecision(
                    is_healthy=False,
                    rollback_required=True,
                    trigger_reason=f"False completion claim detected in turn {r.turn_id}",
                    model_caused_error_rate=1.0,
                    total_window_size=len(self._history),
                    consecutive_model_failures=1,
                )

        # 2. Trigger: Consecutive model-caused errors
        consecutive = 0
        for r in reversed(self._history):
            if r.failure_cause == "model_caused":
                consecutive += 1
            else:
                break

        if consecutive >= self.max_consecutive:
            return HealthDecision(
                is_healthy=False,
                rollback_required=True,
                trigger_reason=f"{consecutive} consecutive model-caused failures",
                model_caused_error_rate=consecutive / len(self._history),
                total_window_size=len(self._history),
                consecutive_model_failures=consecutive,
            )

        # 3. Trigger: Model error rate over window
        model_errors = sum(1 for r in self._history if r.failure_cause == "model_caused")
        error_rate = model_errors / len(self._history)

        if len(self._history) >= 10 and error_rate > self.max_error_rate:
            return HealthDecision(
                is_healthy=False,
                rollback_required=True,
                trigger_reason=(
                    f"Model-caused error rate {error_rate:.1%} exceeds threshold {self.max_error_rate:.1%}"
                ),
                model_caused_error_rate=round(error_rate, 4),
                total_window_size=len(self._history),
                consecutive_model_failures=consecutive,
            )

        return HealthDecision(
            is_healthy=True,
            rollback_required=False,
            trigger_reason="Model operating within acceptable health bounds",
            model_caused_error_rate=round(error_rate, 4),
            total_window_size=len(self._history),
            consecutive_model_failures=consecutive,
        )
