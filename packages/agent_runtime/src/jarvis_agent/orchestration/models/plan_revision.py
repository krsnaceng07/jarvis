"""PlanRevision and PlanDiff models supporting versioned plans (v1, v2, v3)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any

from jarvis_agent.orchestration.models.plan_node import PlanNode


@dataclass(frozen=True, slots=True)
class PlanDiff:
    """Differences between two successive PlanDAG revisions."""

    previous_revision: int
    new_revision: int
    added_nodes: list[PlanNode] = field(default_factory=list)
    modified_node_ids: list[str] = field(default_factory=list)
    removed_node_ids: list[str] = field(default_factory=list)
    preserved_completed_node_ids: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["added_nodes"] = [n.to_dict() for n in self.added_nodes]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanDiff:
        added = [
            PlanNode.from_dict(n) if isinstance(n, dict) else n for n in data.get("added_nodes", [])
        ]
        return cls(
            previous_revision=int(data["previous_revision"]),
            new_revision=int(data["new_revision"]),
            added_nodes=added,
            modified_node_ids=list(data.get("modified_node_ids", [])),
            removed_node_ids=list(data.get("removed_node_ids", [])),
            preserved_completed_node_ids=list(data.get("preserved_completed_node_ids", [])),
            reason=data.get("reason", ""),
        )


@dataclass(frozen=True, slots=True)
class PlanRevision:
    """Versioned record of a PlanDAG iteration."""

    revision_id: str
    plan_id: str
    task_id: str
    revision: int
    plan_hash: str
    diff: PlanDiff | None = None
    created_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.diff is not None:
            d["diff"] = self.diff.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanRevision:
        diff_raw = data.get("diff")
        diff = PlanDiff.from_dict(diff_raw) if isinstance(diff_raw, dict) else diff_raw
        return cls(
            revision_id=data["revision_id"],
            plan_id=data["plan_id"],
            task_id=data["task_id"],
            revision=int(data["revision"]),
            plan_hash=data["plan_hash"],
            diff=diff,
            created_at_utc=data.get(
                "created_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
        )


__all__ = ["PlanDiff", "PlanRevision"]
