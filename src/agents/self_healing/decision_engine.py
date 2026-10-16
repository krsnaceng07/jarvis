"""src.agents.self_healing.decision_engine — Central recovery decision and orchestration engine.

OpenClaw parity: mirrors resolveRunFailoverDecision, attempt-recovery, and
execution loop failover controllers.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence

from .audit_ledger import RecoveryAuditLedger
from .failure_event import ErrorCategory, FailureEvent
from .loop_prevention import LoopPreventionEngine
from .strategies import (
    ProviderFallbackStrategy,
    RecoveryResult,
    ToolArgumentRepairStrategy,
    ToolFallbackStrategy,
    TransientRetryStrategy,
)
from .truthful_escalator import TruthfulEscalationFormatter


class RecoveryAction(str, Enum):
    """Actions the recovery decision engine can recommend."""

    RETRY_WITH_BACKOFF = "retry_with_backoff"
    REPAIR_ARGUMENTS = "repair_arguments"
    FALLBACK_TOOL = "fallback_tool"
    FALLBACK_PROVIDER = "fallback_provider"
    RESTART_PROCESS = "restart_process"
    CONTINUE_INCOMPLETE_TURN = "continue_incomplete_turn"
    ESCALATE_TO_USER = "escalate_to_user"


#: OpenClaw parity continuation instructions from src/agents/embedded-agent-runner/run/incomplete-turn-recovery.ts
REASONING_ONLY_RETRY_INSTRUCTION: str = (
    "The previous assistant turn recorded reasoning but did not produce a user-visible answer. "
    "Continue from that partial turn and produce the visible answer now. Do not restate the reasoning or restart from scratch."
)
EMPTY_RESPONSE_RETRY_INSTRUCTION: str = (
    "The previous attempt did not produce a user-visible answer. Continue from the current state "
    "and produce the visible answer now. Do not restart from scratch."
)
SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION: str = (
    "The previous assistant turn completed its tool calls but did not produce a user-visible answer. "
    "Continue from the current transcript and produce the final user-visible answer now. "
    "Do not repeat completed tool calls or restart from scratch."
)


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    """Actionable decision returned by the engine."""

    action: RecoveryAction
    reason: str
    strategy_name: str = "none"
    backoff_delay_sec: float = 0.0
    repaired_args: dict[str, Any] | None = None
    fallback_target: str | None = None
    continuation_instruction: str | None = None
    abort_task: bool = False


class RecoveryDecisionEngine:
    """Central coordinator for self-healing, loop prevention, and recovery execution."""

    def __init__(
        self,
        loop_prevention: LoopPreventionEngine | None = None,
        audit_ledger: RecoveryAuditLedger | None = None,
    ) -> None:
        self.loop_prevention = loop_prevention or LoopPreventionEngine()
        self.audit_ledger = audit_ledger or RecoveryAuditLedger()

        # Instantiate strategies
        self.transient_strategy = TransientRetryStrategy()
        self.repair_strategy = ToolArgumentRepairStrategy()
        self.tool_fallback_strategy = ToolFallbackStrategy()
        self.provider_fallback_strategy = ProviderFallbackStrategy()

    def evaluate_decision(self, event: FailureEvent) -> RecoveryDecision:
        """Evaluate a FailureEvent and determine the optimal recovery action."""
        # 1. Check loop prevention circuit breaker first
        allowed, block_reason = self.loop_prevention.can_attempt_recovery(
            event.signature, event.category
        )
        if not allowed:
            return RecoveryDecision(
                action=RecoveryAction.ESCALATE_TO_USER,
                reason=block_reason or "Recovery circuit breaker tripped.",
                abort_task=True,
            )

        # 2. Permanent non-recoverable categories
        if event.category == ErrorCategory.AUTH_PERMANENT:
            return RecoveryDecision(
                action=RecoveryAction.ESCALATE_TO_USER,
                reason="Permanent authentication failure (invalid credentials or forbidden account).",
                abort_task=True,
            )

        # 3. Tool argument validation error -> Repair Arguments
        if event.category == ErrorCategory.TOOL_VALIDATION_ERROR:
            return RecoveryDecision(
                action=RecoveryAction.REPAIR_ARGUMENTS,
                reason="Tool argument schema mismatch; attempting heuristic parameter repair.",
                strategy_name=self.repair_strategy.name,
            )

        # 4. Transient network or Rate limit -> Exponential Backoff
        if event.category in (ErrorCategory.NETWORK_TRANSIENT, ErrorCategory.RATE_LIMIT):
            return RecoveryDecision(
                action=RecoveryAction.RETRY_WITH_BACKOFF,
                reason="Transient network or rate limit failure; backing off with jitter.",
                strategy_name=self.transient_strategy.name,
            )

        # 5. Model Overloaded (503) -> Retry first, then Provider Fallback
        if event.category == ErrorCategory.MODEL_OVERLOADED:
            if event.attempt_count <= 1:
                return RecoveryDecision(
                    action=RecoveryAction.RETRY_WITH_BACKOFF,
                    reason="Model overloaded (HTTP 503); initial backoff retry.",
                    strategy_name=self.transient_strategy.name,
                )
            return RecoveryDecision(
                action=RecoveryAction.FALLBACK_PROVIDER,
                reason="Model persistently overloaded; rotating to secondary provider.",
                strategy_name=self.provider_fallback_strategy.name,
            )

        # 6. Tool execution or System I/O errors -> Argument repair or Fallback tool
        if event.category in (ErrorCategory.TOOL_EXECUTION_ERROR, ErrorCategory.SYSTEM_IO_ERROR):
            tool_name = str(event.context.get("tool_name") or "")
            args = event.context.get("args") or {}

            # First attempt: try repairing path syntax / aliases
            repaired_args, changes = self.repair_strategy.repair_arguments(tool_name, args)
            if changes:
                return RecoveryDecision(
                    action=RecoveryAction.REPAIR_ARGUMENTS,
                    reason=f"Path or parameter error; applying repairs: {'; '.join(changes)}",
                    strategy_name=self.repair_strategy.name,
                    repaired_args=repaired_args,
                )

            # Second attempt: check if tool fallback exists
            if tool_name in ("ls", "read"):
                return RecoveryDecision(
                    action=RecoveryAction.FALLBACK_TOOL,
                    reason=f"Specialized tool '{tool_name}' failed; switching to fallback command.",
                    strategy_name=self.tool_fallback_strategy.name,
                )

            # Otherwise escalate to user
            return RecoveryDecision(
                action=RecoveryAction.ESCALATE_TO_USER,
                reason=f"Unrecoverable tool execution error for '{tool_name}': {event.error_message}",
                abort_task=False,
            )

        # 7. Empty response or Reasoning-only deadlock (OpenClaw parity)
        if event.category == ErrorCategory.EMPTY_RESPONSE:
            if event.attempt_count <= 1:
                has_tools = bool(event.context.get("has_completed_tools"))
                instruction = (
                    SETTLED_TOOL_TERMINAL_CONTINUATION_INSTRUCTION
                    if has_tools
                    else EMPTY_RESPONSE_RETRY_INSTRUCTION
                )
                return RecoveryDecision(
                    action=RecoveryAction.CONTINUE_INCOMPLETE_TURN,
                    reason="Model returned empty response; injecting continuation instruction.",
                    continuation_instruction=instruction,
                )
            return RecoveryDecision(
                action=RecoveryAction.FALLBACK_PROVIDER,
                reason="Model persistently returned empty responses; falling back to alternative provider.",
                strategy_name=self.provider_fallback_strategy.name,
            )

        if event.category == ErrorCategory.REASONING_ONLY:
            if event.attempt_count <= 2:
                return RecoveryDecision(
                    action=RecoveryAction.CONTINUE_INCOMPLETE_TURN,
                    reason="Model output reasoning without visible content; injecting continuation instruction.",
                    continuation_instruction=REASONING_ONLY_RETRY_INSTRUCTION,
                )
            return RecoveryDecision(
                action=RecoveryAction.FALLBACK_PROVIDER,
                reason="Model persistently locked in reasoning loop; falling back to alternative provider.",
                strategy_name=self.provider_fallback_strategy.name,
            )

        # 8. Billing exhausted, TLS error, Model not found -> Immediate Provider Fallback
        if event.category == ErrorCategory.BILLING_EXHAUSTED:
            return RecoveryDecision(
                action=RecoveryAction.FALLBACK_PROVIDER,
                reason="Provider quota or billing exhausted; rotating to alternative provider.",
                strategy_name=self.provider_fallback_strategy.name,
            )

        if event.category == ErrorCategory.TLS_CERTIFICATE_ERROR:
            return RecoveryDecision(
                action=RecoveryAction.FALLBACK_PROVIDER,
                reason="TLS certificate verification failure; rotating provider endpoint.",
                strategy_name=self.provider_fallback_strategy.name,
            )

        if event.category == ErrorCategory.MODEL_NOT_FOUND:
            return RecoveryDecision(
                action=RecoveryAction.FALLBACK_PROVIDER,
                reason="Specified model not found on provider; rotating to fallback model.",
                strategy_name=self.provider_fallback_strategy.name,
            )

        # 9. Session expired -> Reconnect with backoff
        if event.category == ErrorCategory.SESSION_EXPIRED:
            return RecoveryDecision(
                action=RecoveryAction.RETRY_WITH_BACKOFF,
                reason="Session expired; re-establishing connection with backoff.",
                strategy_name=self.transient_strategy.name,
            )

        # 10. Tool timeout -> Escalate or retry once
        if event.category == ErrorCategory.TOOL_TIMEOUT:
            if event.attempt_count <= 1:
                return RecoveryDecision(
                    action=RecoveryAction.RETRY_WITH_BACKOFF,
                    reason="Tool timed out; single retry with extended backoff.",
                    strategy_name=self.transient_strategy.name,
                )
            return RecoveryDecision(
                action=RecoveryAction.ESCALATE_TO_USER,
                reason="Tool execution timed out repeatedly.",
                abort_task=True,
            )

        # Default fallback
        return RecoveryDecision(
            action=RecoveryAction.ESCALATE_TO_USER,
            reason=f"Unclassified failure ({event.category.value}): {event.error_message}",
            abort_task=True,
        )

    async def execute_recovery(
        self,
        event: FailureEvent,
        session_key: str = "desktop:hud",
    ) -> tuple[RecoveryDecision, RecoveryResult]:
        """Orchestrate evaluation, strategy execution, audit logging, and loop tracking."""
        decision = self.evaluate_decision(event)

        if decision.action == RecoveryAction.ESCALATE_TO_USER:
            result = RecoveryResult(
                success=False,
                action_taken="Escalated to operator",
                error=decision.reason,
            )
            self.loop_prevention.record_attempt(
                event.signature, action="escalate_to_user", success=False
            )
            self.audit_ledger.record_recovery_event(
                event,
                action="escalate_to_user",
                verified=False,
                details={"reason": decision.reason},
                session_key=session_key,
            )
            return decision, result

        # Dispatch strategy
        if decision.action == RecoveryAction.RETRY_WITH_BACKOFF:
            result = await self.transient_strategy.execute(event)
        elif decision.action == RecoveryAction.REPAIR_ARGUMENTS:
            result = await self.repair_strategy.execute(event)
        elif decision.action == RecoveryAction.FALLBACK_TOOL:
            result = await self.tool_fallback_strategy.execute(event)
        elif decision.action == RecoveryAction.FALLBACK_PROVIDER:
            result = await self.provider_fallback_strategy.execute(event)
        elif decision.action == RecoveryAction.CONTINUE_INCOMPLETE_TURN:
            instruction = decision.continuation_instruction or EMPTY_RESPONSE_RETRY_INSTRUCTION
            result = RecoveryResult(
                success=True,
                action_taken=f"Injected continuation instruction: {instruction[:60]}...",
                requires_retry=True,
                details={"continuation_instruction": instruction},
            )
        else:
            result = RecoveryResult(
                success=False,
                action_taken="Unknown action",
                error=f"Unsupported action {decision.action}",
            )

        # Record attempt in loop prevention and audit ledger
        self.loop_prevention.record_attempt(
            event.signature,
            action=decision.action.value,
            success=result.success,
            details=result.details,
        )
        self.audit_ledger.record_recovery_event(
            event,
            action=decision.action.value,
            verified=result.success,
            details=result.details,
            session_key=session_key,
        )

        return decision, result

    def format_truthful_escalation(
        self,
        completed_steps: Sequence[str] | None,
        failed_step: str,
        error_message: str,
        retry_boundary_reason: str,
        next_steps: Sequence[str] | None = None,
        tool_name: str | None = None,
    ) -> str:
        """Format an anti-hallucination escalation message."""
        return TruthfulEscalationFormatter.format_escalation(
            completed_steps=completed_steps,
            failed_step=failed_step,
            error_message=error_message,
            retry_boundary_reason=retry_boundary_reason,
            next_steps=next_steps,
            tool_name=tool_name,
        )


__all__ = [
    "RecoveryAction",
    "RecoveryDecision",
    "RecoveryDecisionEngine",
]
