"""Topological Dependency DAG Resolver and Eligibility Evaluator for Track 3.3.

HARD INVARIANTS:
1. A node is ELIGIBLE iff:
   - Its current state is PENDING or BLOCKED.
   - ALL predecessor nodes are in state VERIFIED.
   - None of its predecessors are FAILED, CANCELLED, or AMBIGUOUS (unless explicitly modeled as error-handling).
2. Deterministic topological sorting detects cycles and finds maximal parallel executable sets.
3. Zero LLM calls: dependency evaluation is 100% deterministic graph algebra.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from jarvis_agent.orchestration.models.plan import PlanDAG
from jarvis_agent.scheduling.models.node_state import SchedulerNodeState


@dataclass(frozen=True, slots=True)
class EligibilityEvaluation:
    """Result of evaluating a node's readiness for scheduling."""

    node_id: str
    is_eligible: bool
    unmet_dependencies: list[str] = field(default_factory=list)
    failed_dependencies: list[str] = field(default_factory=list)
    blocking_reason: str | None = None


class DependencyEngine:
    """Evaluates PlanDAG node dependencies and identifies maximal parallel executable batches."""

    @staticmethod
    def evaluate_node(
        node_id: str,
        plan: PlanDAG,
        node_states: dict[str, SchedulerNodeState],
    ) -> EligibilityEvaluation:
        """Evaluate if a specific node is eligible to run."""
        if node_id not in plan.nodes:
            return EligibilityEvaluation(
                node_id=node_id,
                is_eligible=False,
                blocking_reason=f"Node {node_id} does not exist in PlanDAG",
            )

        node = plan.nodes[node_id]
        current_state = node_states.get(node_id, SchedulerNodeState.PENDING)

        # Node must be PENDING, BLOCKED, or already ELIGIBLE to be eligible
        if current_state not in (
            SchedulerNodeState.PENDING,
            SchedulerNodeState.BLOCKED,
            SchedulerNodeState.ELIGIBLE,
        ):
            return EligibilityEvaluation(
                node_id=node_id,
                is_eligible=False,
                blocking_reason=f"Node {node_id} is in state {current_state.value}, not PENDING/BLOCKED/ELIGIBLE",
            )

        unmet: list[str] = []
        failed: list[str] = []

        for dep_id in node.dependencies:
            dep_state = node_states.get(dep_id, SchedulerNodeState.PENDING)
            if dep_state == SchedulerNodeState.VERIFIED:
                continue
            elif dep_state in (SchedulerNodeState.FAILED, SchedulerNodeState.CANCELLED):
                failed.append(f"{dep_id}({dep_state.value})")
            else:
                unmet.append(f"{dep_id}({dep_state.value})")

        if failed:
            return EligibilityEvaluation(
                node_id=node_id,
                is_eligible=False,
                failed_dependencies=failed,
                blocking_reason=f"Prerequisite failure: {', '.join(failed)}",
            )

        if unmet:
            return EligibilityEvaluation(
                node_id=node_id,
                is_eligible=False,
                unmet_dependencies=unmet,
                blocking_reason=f"Waiting for prerequisites: {', '.join(unmet)}",
            )

        return EligibilityEvaluation(
            node_id=node_id,
            is_eligible=True,
        )

    @staticmethod
    def get_runnable_nodes(
        plan: PlanDAG,
        node_states: dict[str, SchedulerNodeState],
    ) -> list[str]:
        """Return all nodes that are currently eligible for scheduling."""
        runnable: list[str] = []
        for node_id in plan.nodes:
            eval_res = DependencyEngine.evaluate_node(node_id, plan, node_states)
            if eval_res.is_eligible:
                runnable.append(node_id)
        return runnable

    @staticmethod
    def detect_cycles(plan: PlanDAG) -> list[list[str]]:
        """Detect any circular dependencies in the PlanDAG using DFS coloring."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {nid: WHITE for nid in plan.nodes}
        cycles: list[list[str]] = []

        def dfs(u: str, path: list[str]) -> None:
            color[u] = GRAY
            path.append(u)
            node = plan.nodes.get(u)
            if node:
                for v in node.dependencies:
                    if v not in color:
                        continue
                    if color[v] == GRAY:
                        # Cycle found
                        idx = path.index(v)
                        cycles.append(path[idx:] + [v])
                    elif color[v] == WHITE:
                        dfs(v, path)
            path.pop()
            color[u] = BLACK

        for nid in plan.nodes:
            if color[nid] == WHITE:
                dfs(nid, [])

        return cycles

    @staticmethod
    def get_topological_batches(plan: PlanDAG) -> list[list[str]]:
        """Partition nodes into dependency-ordered parallel tiers."""
        in_degree: dict[str, int] = {}
        dependents: dict[str, list[str]] = {nid: [] for nid in plan.nodes}

        for nid, node in plan.nodes.items():
            in_degree[nid] = len(node.dependencies)
            for dep in node.dependencies:
                if dep in dependents:
                    dependents[dep].append(nid)

        current_batch = [nid for nid, deg in in_degree.items() if deg == 0]
        batches: list[list[str]] = []

        while current_batch:
            batches.append(sorted(current_batch))
            next_batch: list[str] = []
            for u in current_batch:
                for v in dependents.get(u, []):
                    in_degree[v] -= 1
                    if in_degree[v] == 0:
                        next_batch.append(v)
            current_batch = next_batch

        return batches


__all__ = ["DependencyEngine", "EligibilityEvaluation"]
