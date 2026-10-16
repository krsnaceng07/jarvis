"""DecisionPolicyGate enforcing Risk x Capability x Approval authorization invariants."""

from __future__ import annotations

from dataclasses import dataclass

from jarvis_agent.orchestration.models import (
    ApprovalStatus,
    PlanNode,
    RiskClass,
)
from jarvis_agent.orchestration.state.reducer import RuntimeState


@dataclass(frozen=True, slots=True)
class PolicyAuthorizationResult:
    """Outcome of evaluating policy authorization for an execution step."""

    is_authorized: bool
    requires_approval: bool
    reason: str


class DecisionPolicyGate:
    """Security authority determining whether a proposed plan node may be dispatched."""

    def __init__(self, enforce_global_operator_approval: bool = False) -> None:
        self._global_approval = enforce_global_operator_approval

    def authorize_node_execution(
        self,
        node: PlanNode,
        runtime_state: RuntimeState,
    ) -> PolicyAuthorizationResult:
        """Evaluate authorization to execute node."""
        risk = node.risk_assessment
        risk_class = risk.risk_class

        # Check global override
        if self._global_approval and risk_class != RiskClass.READ_ONLY:
            return PolicyAuthorizationResult(
                is_authorized=False,
                requires_approval=True,
                reason="Global operator approval policy is enforced for all mutations.",
            )

        # High or Critical risk operations mandate explicit operator approval
        if risk_class in (RiskClass.HIGH, RiskClass.CRITICAL) or risk.requires_operator_approval:
            approval = runtime_state.approvals.get(node.node_id)
            if not approval:
                return PolicyAuthorizationResult(
                    is_authorized=False,
                    requires_approval=True,
                    reason=f"Node {node.node_id} ({risk_class.value}) requires operator approval; none requested.",
                )
            if approval.status != ApprovalStatus.GRANTED:
                return PolicyAuthorizationResult(
                    is_authorized=False,
                    requires_approval=True,
                    reason=f"Node {node.node_id} approval status is {approval.status.value}; not GRANTED.",
                )
            # Verify argument hash matches bound approval
            if not approval.validate_arguments(node.arguments):
                return PolicyAuthorizationResult(
                    is_authorized=False,
                    requires_approval=True,
                    reason="Node arguments have drifted from authorized approval hash; re-approval required.",
                )
            return PolicyAuthorizationResult(
                is_authorized=True,
                requires_approval=False,
                reason="Explicit operator approval granted and verified against argument hash.",
            )

        # Read-only or low risk local operations are authorized by default
        return PolicyAuthorizationResult(
            is_authorized=True,
            requires_approval=False,
            reason=f"Operation authorized under {risk_class.value} risk policy.",
        )


__all__ = ["DecisionPolicyGate", "PolicyAuthorizationResult"]
