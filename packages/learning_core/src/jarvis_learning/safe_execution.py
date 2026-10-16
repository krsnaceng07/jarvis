"""jarvis_learning.safe_execution — Complete safe execution boundary.

Enforces the strict execution chain:
  Local prediction
  → deterministic argument builder
  → schema validation
  → policy/risk validation
  → authorization check (Confidence ≠ Permission)
  → canonical executor
  → physical verification
  → truthful outcome

Any failure safely aborts local execution and routes to foundation LLM fallback.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .models.arguments import DeterministicArgumentBuilder
from .models.base import ToolPrediction
from .routing.guard import LocalDecisionGuard
from .routing.router import RoutingState
from .truthfulness import OutcomeClass, TruthfulCompletionEnforcer, TruthfulOutcome


@dataclass(frozen=True, slots=True)
class SafeExecutionResult:
    """Outcome of safe execution attempt."""

    executed: bool
    fallback_to_llm: bool
    abort_reason: Optional[str]
    tool_name: str
    tool_arguments: dict[str, Any]
    raw_result: Any
    truthful_outcome: Optional[TruthfulOutcome]
    routing_state: RoutingState


class SafeExecutionBoundary:
    """Orchestrates multi-stage pre-execution gating, execution, and verification."""

    def __init__(
        self,
        arg_builder: Optional[DeterministicArgumentBuilder] = None,
        decision_guard: Optional[LocalDecisionGuard] = None,
        truthfulness_enforcer: Optional[TruthfulCompletionEnforcer] = None,
    ) -> None:
        self.arg_builder = arg_builder or DeterministicArgumentBuilder()
        self.decision_guard = decision_guard or LocalDecisionGuard()
        self.truthfulness_enforcer = truthfulness_enforcer or TruthfulCompletionEnforcer()

    def attempt_execution(
        self,
        prediction: ToolPrediction,
        user_input: str,
        context: dict[str, Any],
        tool_executor_fn: Callable[[str, dict[str, Any]], Any],
        verifier_fn: Optional[Callable[[str, dict[str, Any], Any], Any]] = None,
        schema_validator_fn: Optional[
            Callable[[str, dict[str, Any]], tuple[dict[str, Any], Optional[str]]]
        ] = None,
        operator_authorized: bool = False,
        local_models_enabled: bool = False,
    ) -> SafeExecutionResult:
        """Execute full safety chain for a local model prediction."""
        # 1. Check local model enablement
        if not local_models_enabled:
            return SafeExecutionResult(
                executed=False,
                fallback_to_llm=True,
                abort_reason="Local models disabled by configuration",
                tool_name=prediction.tool_name,
                tool_arguments={},
                raw_result=None,
                truthful_outcome=None,
                routing_state=RoutingState.SHADOW_ONLY,
            )

        # 2. Strict authorization check: Confidence != Permission
        # High confidence alone NEVER grants autonomous execution permission without authorization
        if not operator_authorized:
            return SafeExecutionResult(
                executed=False,
                fallback_to_llm=True,
                abort_reason="Confidence does not equal permission; operator authorization required for fast-path",
                tool_name=prediction.tool_name,
                tool_arguments={},
                raw_result=None,
                truthful_outcome=None,
                routing_state=RoutingState.ADVISORY_ELIGIBLE,
            )

        # 3. Deterministic argument builder
        arg_result = self.arg_builder.build_arguments(prediction.tool_name, user_input, context)
        if not arg_result.success:
            return SafeExecutionResult(
                executed=False,
                fallback_to_llm=True,
                abort_reason=f"Argument builder required LLM reasoning ({arg_result.reason})",
                tool_name=prediction.tool_name,
                tool_arguments={},
                raw_result=None,
                truthful_outcome=None,
                routing_state=RoutingState.ADVISORY_ELIGIBLE,
            )

        built_args = arg_result.arguments

        # 4. Schema validation (e.g. via ToolSchemaRegistry or custom schema validator)
        if schema_validator_fn is not None:
            coerced_args, schema_err = schema_validator_fn(prediction.tool_name, built_args)
            if schema_err:
                return SafeExecutionResult(
                    executed=False,
                    fallback_to_llm=True,
                    abort_reason=f"Schema validation failed: {schema_err}",
                    tool_name=prediction.tool_name,
                    tool_arguments=built_args,
                    raw_result=None,
                    truthful_outcome=None,
                    routing_state=RoutingState.ERROR_SAFE_FALLBACK,
                )
            built_args = coerced_args

        # 5. Policy and risk validation via LocalDecisionGuard
        guard_decision = self.decision_guard.validate(prediction, context)
        if not guard_decision.allowed:
            return SafeExecutionResult(
                executed=False,
                fallback_to_llm=True,
                abort_reason=f"LocalDecisionGuard blocked action ({guard_decision.reason})",
                tool_name=prediction.tool_name,
                tool_arguments=built_args,
                raw_result=None,
                truthful_outcome=None,
                routing_state=RoutingState.POLICY_DENIED,
            )

        # 6. Execute via canonical tool executor
        try:
            raw_result = tool_executor_fn(prediction.tool_name, built_args)
        except Exception as exc:
            return SafeExecutionResult(
                executed=False,
                fallback_to_llm=True,
                abort_reason=f"Canonical tool executor raised exception: {exc}",
                tool_name=prediction.tool_name,
                tool_arguments=built_args,
                raw_result=None,
                truthful_outcome=TruthfulOutcome(
                    outcome_class=OutcomeClass.FAILED,
                    verified=False,
                    tool_name=prediction.tool_name,
                    error=str(exc),
                    truthful_message=f"Tool execution raised exception: {exc}",
                    allows_definitive_completion=False,
                ),
                routing_state=RoutingState.ERROR_SAFE_FALLBACK,
            )

        # 7. Physical outcome verification
        v_outcome = None
        if verifier_fn is not None:
            try:
                v_outcome = verifier_fn(prediction.tool_name, built_args, raw_result)
            except Exception as v_exc:
                v_outcome = {
                    "status": "verifier_error",
                    "verified": False,
                    "error": str(v_exc),
                }

        # 8. Truthful outcome classification
        truthful_outcome = self.truthfulness_enforcer.evaluate_outcome(
            tool_name=prediction.tool_name,
            tool_args=built_args,
            tool_result=raw_result,
            verifier_outcome=v_outcome,
        )

        return SafeExecutionResult(
            executed=True,
            fallback_to_llm=False,
            abort_reason=None,
            tool_name=prediction.tool_name,
            tool_arguments=built_args,
            raw_result=raw_result,
            truthful_outcome=truthful_outcome,
            routing_state=RoutingState.PRODUCTION_ACTIVE,
        )
