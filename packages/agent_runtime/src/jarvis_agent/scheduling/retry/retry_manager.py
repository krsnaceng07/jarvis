"""Side-effect aware retry policies, decisions, and loop prevention fingerprints for Track 3.3.

HARD INVARIANTS:
1. Integration with Track 3.2 SideEffectClass:
   - READ_ONLY: retryable with exponential backoff.
   - IDEMPOTENT_MUTATION: retryable if arguments hash matches.
   - NON_IDEMPOTENT_MUTATION: NON-RETRYABLE without plan revision -> REPLAN.
   - EXTERNAL_TRANSACTION: NON-RETRYABLE -> ESCALATE / REPLAN.
2. 3-Strike Loop Detector:
   - If (task_id, node_id, failure_class, arguments_hash, plan_revision) repeats >= 3 times,
     break retry cycle and trigger ESCALATE / REPLAN.
"""

from __future__ import annotations

import collections
import logging

from jarvis_agent.execution.errors.taxonomy import ExecutionFailureClass
from jarvis_agent.execution.models.capability_definition import SideEffectClass
from jarvis_agent.execution.models.execution_result import ExecutionResult, ExecutionStatus
from jarvis_agent.scheduling.models.retry import (
    RecoveryAction,
    RetryDecision,
    RetryPolicy,
    compute_recovery_fingerprint,
)

logger = logging.getLogger(__name__)


class RetryManager:
    """Evaluates failed executions and determines recovery decisions."""

    def __init__(
        self,
        policy: RetryPolicy | None = None,
        max_loop_count: int = 3,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self.max_loop_count = max_loop_count
        self._fingerprint_counts: dict[str, int] = collections.defaultdict(int)

    def evaluate_failure(
        self,
        result: ExecutionResult,
        side_effect_class: SideEffectClass,
        arguments_hash: str,
        current_attempt: int,
        max_attempts: int,
    ) -> RetryDecision:
        """Evaluate an execution failure and return the authoritative recovery decision."""
        # Check non-failure states
        if result.status == ExecutionStatus.VERIFIED:
            return RetryDecision(
                action=RecoveryAction.FAIL,
                reason="Node succeeded; cannot evaluate retry on verified execution",
            )

        # Parse failure class
        raw_fc = result.failure_class or "UNKNOWN"
        try:
            fc = ExecutionFailureClass(raw_fc)
        except ValueError:
            fc = ExecutionFailureClass.INTERNAL_ERROR

        # Calculate recovery fingerprint for 3-strike loop prevention
        fp = compute_recovery_fingerprint(
            task_id=result.task_id,
            node_id=result.node_id,
            failure_class=fc.value,
            arguments_hash=arguments_hash,
            plan_revision=result.plan_revision,
        )
        self._fingerprint_counts[fp] += 1
        repeat_count = self._fingerprint_counts[fp]

        if repeat_count >= self.max_loop_count:
            return RetryDecision(
                action=RecoveryAction.ESCALATE,
                reason=f"3-strike recovery loop detected ({repeat_count} identical failures) for fingerprint {fp[:8]}",
                fingerprint=fp,
            )

        # Non-retryable failure classes
        non_retryable_classes = {
            ExecutionFailureClass.INVALID_COMMAND,
            ExecutionFailureClass.INVALID_ARGUMENTS,
            ExecutionFailureClass.POLICY_DENIED,
            ExecutionFailureClass.PERMISSION_DENIED,
            ExecutionFailureClass.SANDBOX_DENIED,
            ExecutionFailureClass.IDEMPOTENCY_CONFLICT,
            ExecutionFailureClass.STALE_COMMAND,
        }
        if fc in non_retryable_classes:
            return RetryDecision(
                action=RecoveryAction.FAIL,
                reason=f"Failure class {fc.value} is non-retryable",
                fingerprint=fp,
            )

        # State drift / verification failure requires replan from Track 3.1
        if fc in (ExecutionFailureClass.STATE_DRIFT, ExecutionFailureClass.VERIFICATION_FAILURE):
            return RetryDecision(
                action=RecoveryAction.REPLAN,
                reason=f"Verification failed or state drift detected ({fc.value}); requires plan revision",
                fingerprint=fp,
            )

        # SideEffectClass constraints: NON_IDEMPOTENT_MUTATION or EXTERNAL_TRANSACTION cannot be safely retried
        if side_effect_class == SideEffectClass.NON_IDEMPOTENT_MUTATION:
            return RetryDecision(
                action=RecoveryAction.REPLAN,
                reason="Side-effect class NON_IDEMPOTENT_MUTATION cannot be retried without replan",
                fingerprint=fp,
            )
        elif side_effect_class == SideEffectClass.EXTERNAL_TRANSACTION:
            return RetryDecision(
                action=RecoveryAction.ESCALATE,
                reason="Side-effect class EXTERNAL_TRANSACTION cannot be retried; requires operator escalation",
                fingerprint=fp,
            )

        # Attempt count check
        next_attempt = current_attempt + 1
        if next_attempt > max_attempts or next_attempt > self.policy.max_retries:
            return RetryDecision(
                action=RecoveryAction.FAIL,
                reason=f"Max attempts exceeded ({current_attempt}/{max_attempts})",
                fingerprint=fp,
            )

        # Retryable with exponential backoff
        delay = self.policy.calculate_delay(current_attempt)
        return RetryDecision(
            action=RecoveryAction.RETRY,
            reason=f"Retryable failure ({fc.value}); scheduling attempt {next_attempt} after {delay:.1f}s delay",
            delay_seconds=delay,
            next_attempt_id=next_attempt,
            fingerprint=fp,
        )

    def reset_fingerprint(self, fingerprint: str) -> None:
        """Reset failure count upon successful execution or plan revision."""
        if fingerprint in self._fingerprint_counts:
            del self._fingerprint_counts[fingerprint]


__all__ = ["RetryManager"]
