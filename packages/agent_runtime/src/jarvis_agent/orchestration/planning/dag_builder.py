"""Builder for constructing validated, immutable PlanDAGs."""

from __future__ import annotations

import uuid
from typing import Any

from jarvis_agent.orchestration.models import (
    NodeStatus,
    ObservationRequirement,
    PlanDAG,
    PlanNode,
    RiskAssessment,
    VerificationRequirement,
)
from jarvis_agent.orchestration.planning.plan_validator import PlanValidator


class PlanDAGBuilder:
    """Fluent builder for constructing valid PlanDAG execution graphs."""

    def __init__(self, validator: PlanValidator | None = None) -> None:
        self._nodes: dict[str, PlanNode] = {}
        self._validator = validator or PlanValidator()

    def add_node(
        self,
        node_id: str,
        goal: str,
        capability: str,
        arguments: dict[str, Any] | None = None,
        dependencies: list[str] | None = None,
        risk_assessment: RiskAssessment | None = None,
        observation_requirements: list[ObservationRequirement] | None = None,
        verification_requirements: list[VerificationRequirement] | None = None,
        max_attempts: int = 3,
        timeout_seconds: float = 120.0,
    ) -> PlanDAGBuilder:
        """Add an execution step to the plan under construction."""
        node = PlanNode(
            node_id=node_id,
            plan_id="",  # Bound at build() time
            goal=goal,
            capability=capability,
            arguments=arguments or {},
            dependencies=list(dependencies or []),
            status=NodeStatus.PENDING,
            risk_assessment=risk_assessment or RiskAssessment.safe_read_only(),
            observation_requirements=list(observation_requirements or []),
            verification_requirements=list(verification_requirements or []),
            max_attempts=max_attempts,
            timeout_seconds=timeout_seconds,
        )
        self._nodes[node_id] = node
        return self

    def build(
        self,
        task_id: str,
        plan_id: str | None = None,
        revision: int = 1,
        validate: bool = True,
    ) -> PlanDAG:
        """Construct the immutable PlanDAG and optionally run validation audit."""
        pid = plan_id or f"plan_{uuid.uuid4().hex[:12]}"
        bound_nodes = {
            nid: PlanNode.from_dict({**node.to_dict(), "plan_id": pid})
            for nid, node in self._nodes.items()
        }
        dag = PlanDAG(plan_id=pid, task_id=task_id, revision=revision, nodes=bound_nodes)

        if validate:
            res = self._validator.validate(dag)
            if not res.is_valid:
                raise ValueError(f"Constructed PlanDAG failed validation: {'; '.join(res.errors)}")

        return dag


__all__ = ["PlanDAGBuilder"]
