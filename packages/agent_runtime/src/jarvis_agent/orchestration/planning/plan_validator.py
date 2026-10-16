"""Strict DAG invariant validator enforcing structural and safety integrity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis_agent.orchestration.models import PlanDAG, RiskClass
from jarvis_agent.orchestration.planning.dependency_resolver import DependencyResolver
from jarvis_agent.orchestration.planning.plan_limits import PlanLimits


@dataclass(frozen=True, slots=True)
class PlanValidationResult:
    """Outcome of PlanDAG validation audit."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


class PlanValidator:
    """Validates structural and policy invariants on proposed PlanDAGs."""

    def __init__(self, limits: PlanLimits | None = None) -> None:
        self._limits = limits or PlanLimits()

    def validate(self, plan: PlanDAG) -> PlanValidationResult:
        """Run full invariant validation audit on a PlanDAG."""
        errors: list[str] = []
        warnings: list[str] = []

        # Invariant 1: Non-empty plan
        if not plan.nodes:
            errors.append("Plan contains zero nodes; cannot execute empty plan.")
            return PlanValidationResult(is_valid=False, errors=errors)

        # Invariant 2: Node count within limits
        if len(plan.nodes) > self._limits.max_nodes:
            errors.append(
                f"Plan node count {len(plan.nodes)} exceeds budget limit {self._limits.max_nodes}"
            )

        # Invariant 3: Dependency existence
        missing_deps = DependencyResolver.find_missing_dependencies(plan)
        if missing_deps:
            errors.extend(missing_deps)

        # Invariant 4: No cycles and valid topological order
        if plan.has_cycle():
            errors.append("PlanDAG contains dependency cycles.")
        else:
            depth = DependencyResolver.get_critical_path_depth(plan)
            if depth > self._limits.max_depth:
                errors.append(
                    f"Plan critical path depth {depth} exceeds max depth {self._limits.max_depth}"
                )

        # Invariant 5: Node-level safety contracts
        for nid, node in plan.nodes.items():
            if not node.capability or not node.capability.strip():
                errors.append(f"Node {nid} has empty capability target.")

            # High or critical risk nodes must have verification requirements
            if node.risk_assessment.risk_class in (RiskClass.HIGH, RiskClass.CRITICAL):
                if not node.verification_requirements:
                    errors.append(
                        f"Node {nid} has risk class {node.risk_assessment.risk_class.value} "
                        "but defines no mandatory verification requirements."
                    )

        return PlanValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )


__all__ = ["PlanValidationResult", "PlanValidator"]
