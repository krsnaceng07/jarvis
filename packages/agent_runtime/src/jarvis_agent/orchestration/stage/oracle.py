"""Independent stage machine reference oracle for transition path and reachability verification."""

from __future__ import annotations

from collections import deque

from jarvis_agent.orchestration.models.stage import TaskStage
from jarvis_agent.orchestration.stage.transition_rules import LEGAL_TRANSITIONS, is_transition_legal


class StageReferenceOracle:
    """Independent reference oracle validating stage graph properties and trace validity."""

    @staticmethod
    def verify_trace(stages: list[TaskStage]) -> list[str]:
        """Verify an observed sequence of stage transitions.

        Returns:
            List of violation descriptions. Empty if trace is 100% legal.
        """
        violations: list[str] = []
        if len(stages) <= 1:
            return violations

        for idx in range(len(stages) - 1):
            curr = stages[idx]
            nxt = stages[idx + 1]
            if not is_transition_legal(curr, nxt):
                violations.append(
                    f"Step {idx}: Illegal transition from {curr.value} to {nxt.value}"
                )
        return violations

    @staticmethod
    def is_reachable(from_stage: TaskStage, to_stage: TaskStage) -> bool:
        """Evaluate if to_stage is reachable from from_stage via legal transitions."""
        if from_stage == to_stage:
            return True
        visited: set[TaskStage] = {from_stage}
        queue: deque[TaskStage] = deque([from_stage])

        while queue:
            curr = queue.popleft()
            for neighbor in LEGAL_TRANSITIONS.get(curr, set()):
                if neighbor == to_stage:
                    return True
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return False

    @staticmethod
    def get_reachable_stages(from_stage: TaskStage) -> set[TaskStage]:
        """Compute the set of all reachable stages from from_stage."""
        visited: set[TaskStage] = {from_stage}
        queue: deque[TaskStage] = deque([from_stage])

        while queue:
            curr = queue.popleft()
            for neighbor in LEGAL_TRANSITIONS.get(curr, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        return visited


__all__ = ["StageReferenceOracle"]
