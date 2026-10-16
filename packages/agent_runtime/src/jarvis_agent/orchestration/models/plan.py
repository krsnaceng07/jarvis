"""Immutable PlanDAG model with topological sorting and deterministic canonical hashing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
import datetime
import hashlib
import json
from typing import Any

from jarvis_agent.orchestration.models.plan_node import NodeStatus, PlanNode


@dataclass(frozen=True, slots=True)
class PlanDAG:
    """Immutable Directed Acyclic Execution Graph representing a planned procedure."""

    plan_id: str
    task_id: str
    revision: int
    nodes: dict[str, PlanNode] = field(default_factory=dict)
    created_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def get_node(self, node_id: str) -> PlanNode | None:
        return self.nodes.get(node_id)

    def topological_sort(self) -> list[str]:
        """Compute a deterministic topological sort of the node IDs.

        Raises ValueError if a cycle is detected.
        """
        in_degree: dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: dict[str, list[str]] = {nid: [] for nid in self.nodes}

        for nid, node in self.nodes.items():
            for dep in node.dependencies:
                if dep in self.nodes:
                    adj[dep].append(nid)
                    in_degree[nid] += 1

        # Queue nodes with in_degree 0, sorted by node_id for determinism
        queue = deque(sorted([nid for nid, deg in in_degree.items() if deg == 0]))
        order: list[str] = []

        while queue:
            curr = queue.popleft()
            order.append(curr)
            for neighbor in sorted(adj[curr]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(order) != len(self.nodes):
            unresolved = [nid for nid, deg in in_degree.items() if deg > 0]
            raise ValueError(f"Cycle or unresolved dependency detected in PlanDAG: {unresolved}")

        return order

    def has_cycle(self) -> bool:
        """Return True if the DAG contains a dependency cycle."""
        try:
            self.topological_sort()
            return False
        except ValueError:
            return True

    def get_ready_nodes(self) -> list[PlanNode]:
        """Return all nodes whose dependencies are all COMPLETED and status is READY or PENDING."""
        ready: list[PlanNode] = []
        for node in self.nodes.values():
            if node.status in (NodeStatus.PENDING, NodeStatus.READY):
                deps_satisfied = all(
                    self.nodes.get(dep) is not None
                    and self.nodes[dep].status == NodeStatus.COMPLETED
                    for dep in node.dependencies
                )
                if deps_satisfied:
                    ready.append(node)
        return sorted(ready, key=lambda n: n.node_id)

    def is_completed(self) -> bool:
        """True if all nodes have reached COMPLETED (or SKIPPED)."""
        if not self.nodes:
            return False
        return all(
            n.status in (NodeStatus.COMPLETED, NodeStatus.SKIPPED) for n in self.nodes.values()
        )

    def is_failed(self) -> bool:
        """True if any node has reached terminal FAILED state with no retries remaining."""
        return any(n.status == NodeStatus.FAILED and not n.can_retry() for n in self.nodes.values())

    def compute_plan_hash(self) -> str:
        """Compute deterministic SHA-256 digest of topological node goals, capabilities, and dependencies."""
        topo = self.topological_sort()
        normalized_elements = []
        for nid in topo:
            node = self.nodes[nid]
            normalized_elements.append(
                {
                    "node_id": node.node_id,
                    "goal": node.goal,
                    "capability": node.capability,
                    "dependencies": sorted(node.dependencies),
                    "args": node.arguments,
                }
            )
        canonical_bytes = json.dumps(
            normalized_elements, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical_bytes).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "task_id": self.task_id,
            "revision": self.revision,
            "nodes": {k: v.to_dict() for k, v in self.nodes.items()},
            "created_at_utc": self.created_at_utc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanDAG:
        nodes = {
            k: PlanNode.from_dict(v) if isinstance(v, dict) else v
            for k, v in data.get("nodes", {}).items()
        }
        return cls(
            plan_id=data["plan_id"],
            task_id=data["task_id"],
            revision=int(data.get("revision", 1)),
            nodes=nodes,
            created_at_utc=data.get(
                "created_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
        )


__all__ = ["PlanDAG"]
