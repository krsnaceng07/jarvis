"""ExecutionAttempt model tracking attempt identity and per-attempt telemetry."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any

from jarvis_agent.scheduling.models.node_state import SchedulerNodeState


@dataclass(frozen=True, slots=True)
class ExecutionAttempt:
    """Discrete attempt to execute a PlanNode."""

    attempt_id: int
    node_id: str
    task_id: str
    plan_id: str
    plan_revision: int
    command_id: str
    execution_id: str
    worker_id: str
    status: SchedulerNodeState
    started_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    completed_at_utc: str | None = None
    exit_code: int | None = None
    failure_class: str | None = None
    error_message: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    lease_generation: int = 1

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionAttempt:
        st = data["status"]
        if isinstance(st, str):
            st = SchedulerNodeState(st)
        return cls(
            attempt_id=int(data["attempt_id"]),
            node_id=data["node_id"],
            task_id=data["task_id"],
            plan_id=data["plan_id"],
            plan_revision=int(data.get("plan_revision", 1)),
            command_id=data["command_id"],
            execution_id=data["execution_id"],
            worker_id=data["worker_id"],
            status=st,
            started_at_utc=data.get(
                "started_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            completed_at_utc=data.get("completed_at_utc"),
            exit_code=data.get("exit_code"),
            failure_class=data.get("failure_class"),
            error_message=data.get("error_message"),
            evidence_refs=list(data.get("evidence_refs", [])),
            lease_generation=int(data.get("lease_generation", 1)),
        )


__all__ = ["ExecutionAttempt"]
