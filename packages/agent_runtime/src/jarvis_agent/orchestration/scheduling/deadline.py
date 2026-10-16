"""Hierarchical deadline and timeout evaluator (task -> plan -> node -> attempt)."""

from __future__ import annotations

import datetime

from jarvis_agent.orchestration.models import PlanDAG, PlanNode, Task


class HierarchicalDeadlineEvaluator:
    """Evaluates multi-tier timeouts across task, plan, and node attempts."""

    @staticmethod
    def is_task_expired(
        task: Task,
        limit_seconds: float = 3600.0,
        current_time: datetime.datetime | None = None,
    ) -> bool:
        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        created = datetime.datetime.fromisoformat(task.created_at_utc)
        return (now - created).total_seconds() > limit_seconds

    @staticmethod
    def is_node_expired(
        node: PlanNode,
        current_time: datetime.datetime | None = None,
    ) -> bool:
        if not node.started_at_utc:
            return False
        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        started = datetime.datetime.fromisoformat(node.started_at_utc)
        return (now - started).total_seconds() > node.timeout_seconds

    @classmethod
    def evaluate_deadlines(
        cls,
        task: Task,
        plan: PlanDAG,
        task_timeout_seconds: float = 3600.0,
        current_time: datetime.datetime | None = None,
    ) -> list[str]:
        """Check all in-flight nodes for timeouts. Returns list of expired node IDs."""
        now = current_time or datetime.datetime.now(datetime.timezone.utc)
        expired_nodes: list[str] = []

        for nid, node in plan.nodes.items():
            if node.status.is_in_flight:
                if cls.is_node_expired(node, current_time=now):
                    expired_nodes.append(nid)

        return expired_nodes


__all__ = ["HierarchicalDeadlineEvaluator"]
