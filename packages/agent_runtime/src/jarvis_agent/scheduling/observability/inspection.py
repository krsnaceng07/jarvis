"""Deterministic runtime inspection and explainability APIs for Track 3.3.

Provides machine-checkable answers to:
- Why is my task waiting?
- Why did node X not execute?
- What resource is blocking execution?
- What is the effective deadline?
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any

from jarvis_agent.scheduling.models.node_state import SchedulerNodeState
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


@dataclass(frozen=True, slots=True)
class NodeBlockExplanation:
    """Deterministic explanation of why a node is blocked or not executing."""

    node_id: str
    task_id: str
    state: str
    is_blocked: bool
    blocking_reasons: list[str] = field(default_factory=list)
    resource_locks_holding: list[str] = field(default_factory=list)
    effective_deadline_utc: str | None = None
    is_expired: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SchedulerInspector:
    """Exposes deterministic inspection and explainability methods over the projection store."""

    def __init__(self, store: ProjectionStore) -> None:
        self.store = store

    def explain_block(self, node_id: str) -> NodeBlockExplanation:
        """Deterministically explain why a node is blocked."""
        node_rec = self.store.get_node(node_id)
        if not node_rec:
            return NodeBlockExplanation(
                node_id=node_id,
                task_id="",
                state="UNKNOWN",
                is_blocked=True,
                blocking_reasons=[f"Node {node_id} not found in scheduler projection"],
            )

        task_id = node_rec["task_id"]
        state_str = node_rec["state"]
        sched_state = SchedulerNodeState(state_str)
        deadline_utc = node_rec.get("effective_deadline_utc")

        reasons: list[str] = []
        is_expired = False
        now_dt = datetime.datetime.now(datetime.timezone.utc)

        if deadline_utc:
            try:
                dl_dt = datetime.datetime.fromisoformat(deadline_utc)
                if now_dt > dl_dt:
                    is_expired = True
                    reasons.append(f"Effective deadline expired at {deadline_utc}")
            except Exception:
                pass

        if sched_state == SchedulerNodeState.BLOCKED:
            reasons.append("Waiting for prerequisite DAG nodes to be VERIFIED")
        elif sched_state == SchedulerNodeState.FAILED:
            reasons.append(
                f"Node execution failed: current_attempt={node_rec['current_attempt']}/{node_rec['max_attempts']}"
            )
        elif sched_state == SchedulerNodeState.AMBIGUOUS:
            reasons.append(
                "Unresolved crash ambiguity; awaiting reconciliation or replanner escalation"
            )

        return NodeBlockExplanation(
            node_id=node_id,
            task_id=task_id,
            state=state_str,
            is_blocked=sched_state
            in (SchedulerNodeState.BLOCKED, SchedulerNodeState.FAILED, SchedulerNodeState.AMBIGUOUS)
            or is_expired,
            blocking_reasons=reasons,
            effective_deadline_utc=deadline_utc,
            is_expired=is_expired,
        )


__all__ = ["NodeBlockExplanation", "SchedulerInspector"]
