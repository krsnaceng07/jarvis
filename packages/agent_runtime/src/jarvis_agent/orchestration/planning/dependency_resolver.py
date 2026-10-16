"""Dependency resolution, parallel readiness, and DAG depth calculation."""

from __future__ import annotations

from jarvis_agent.orchestration.models import NodeStatus, PlanDAG, PlanNode


class DependencyResolver:
    """Analyzes node prerequisites, computes critical execution path, and selects parallel-ready nodes."""

    @staticmethod
    def get_parallel_ready_nodes(plan: PlanDAG) -> list[PlanNode]:
        """Return nodes ready for concurrent dispatch (all dependencies COMPLETED and status is READY or PENDING)."""
        ready: list[PlanNode] = []
        for node in plan.nodes.values():
            if node.status in (NodeStatus.PENDING, NodeStatus.READY):
                deps_ok = all(
                    dep in plan.nodes and plan.nodes[dep].status == NodeStatus.COMPLETED
                    for dep in node.dependencies
                )
                if deps_ok:
                    ready.append(node)
        return sorted(ready, key=lambda n: n.node_id)

    @staticmethod
    def get_critical_path_depth(plan: PlanDAG) -> int:
        """Compute the maximum length (depth) of any dependency chain in the plan."""
        if not plan.nodes:
            return 0
        try:
            topo = plan.topological_sort()
        except ValueError:
            return -1  # Cycle detected

        depths: dict[str, int] = {nid: 1 for nid in plan.nodes}
        for nid in topo:
            node = plan.nodes[nid]
            for dep in node.dependencies:
                if dep in depths:
                    depths[nid] = max(depths[nid], depths[dep] + 1)

        return max(depths.values()) if depths else 0

    @staticmethod
    def find_missing_dependencies(plan: PlanDAG) -> list[str]:
        """Return list of dependency IDs that are referenced by nodes but do not exist in the plan."""
        missing: list[str] = []
        for nid, node in plan.nodes.items():
            for dep in node.dependencies:
                if dep not in plan.nodes:
                    missing.append(f"Node {nid} references missing dependency '{dep}'")
        return missing


__all__ = ["DependencyResolver"]
