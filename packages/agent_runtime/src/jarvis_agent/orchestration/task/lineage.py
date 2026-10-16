"""Task parent-child relationship and lineage epoch tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
from typing import Any

from jarvis_agent.orchestration.models.task_identity import TaskIdentity


@dataclass
class LineageNode:
    """Internal node tracking a task and its direct children."""

    identity: TaskIdentity
    child_task_ids: list[str] = field(default_factory=list)
    created_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )


class TaskLineageTracker:
    """Maintains task parent-child hierarchies, epochs, and generation depths."""

    def __init__(self) -> None:
        self._nodes: dict[str, LineageNode] = {}

    def register_task(self, identity: TaskIdentity) -> None:
        """Register a new task identity into the lineage graph."""
        node = LineageNode(identity=identity)
        self._nodes[identity.task_id] = node

        if identity.parent_task_id and identity.parent_task_id in self._nodes:
            parent = self._nodes[identity.parent_task_id]
            if identity.task_id not in parent.child_task_ids:
                parent.child_task_ids.append(identity.task_id)

    def get_identity(self, task_id: str) -> TaskIdentity | None:
        node = self._nodes.get(task_id)
        return node.identity if node else None

    def get_children(self, task_id: str) -> list[str]:
        node = self._nodes.get(task_id)
        return list(node.child_task_ids) if node else []

    def get_root_task_id(self, task_id: str) -> str | None:
        identity = self.get_identity(task_id)
        return identity.root_task_id if identity else None

    def get_generation(self, task_id: str) -> int:
        identity = self.get_identity(task_id)
        return identity.generation if identity else 1

    def is_ancestor(self, ancestor_id: str, descendant_id: str) -> bool:
        """Return True if ancestor_id is an ancestor of descendant_id."""
        curr = self.get_identity(descendant_id)
        visited: set[str] = set()
        while curr and curr.parent_task_id:
            if curr.parent_task_id == ancestor_id:
                return True
            if curr.parent_task_id in visited:
                break
            visited.add(curr.parent_task_id)
            curr = self.get_identity(curr.parent_task_id)
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            tid: {
                "identity": node.identity.to_dict(),
                "child_task_ids": node.child_task_ids,
                "created_at_utc": node.created_at_utc,
            }
            for tid, node in self._nodes.items()
        }


__all__ = ["LineageNode", "TaskLineageTracker"]
