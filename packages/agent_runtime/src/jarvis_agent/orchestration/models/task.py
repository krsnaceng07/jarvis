"""Task model representing the authoritative lifecycle of an autonomous unit of work."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import datetime
from typing import Any

from jarvis_agent.orchestration.models.response_route import ResponseRoute
from jarvis_agent.orchestration.models.stage import TaskStage
from jarvis_agent.orchestration.models.task_identity import TaskIdentity


@dataclass(frozen=True, slots=True)
class Task:
    """Authoritative task entity representing a goal and its progression."""

    identity: TaskIdentity
    goal: str
    current_stage: TaskStage
    response_route: ResponseRoute
    current_plan_id: str | None = None
    current_plan_revision: int = 0
    created_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    updated_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    is_focused: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self.identity.task_id

    @property
    def is_terminal(self) -> bool:
        return self.current_stage.is_terminal

    def with_stage(self, new_stage: TaskStage) -> Task:
        """Return a new Task instance updated with the new stage and updated timestamp."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return replace(self, current_stage=new_stage, updated_at_utc=now_utc)

    def with_plan(self, plan_id: str, revision: int) -> Task:
        """Return a new Task instance updated with active plan ID and revision."""
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return replace(
            self,
            current_plan_id=plan_id,
            current_plan_revision=revision,
            updated_at_utc=now_utc,
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["identity"] = self.identity.to_dict()
        d["current_stage"] = self.current_stage.value
        d["response_route"] = self.response_route.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Task:
        identity = data["identity"]
        if isinstance(identity, dict):
            identity = TaskIdentity.from_dict(identity)
        stage = data["current_stage"]
        if isinstance(stage, str):
            stage = TaskStage(stage)
        route = data["response_route"]
        if isinstance(route, dict):
            route = ResponseRoute.from_dict(route)
        return cls(
            identity=identity,
            goal=data["goal"],
            current_stage=stage,
            response_route=route,
            current_plan_id=data.get("current_plan_id"),
            current_plan_revision=int(data.get("current_plan_revision", 0)),
            created_at_utc=data.get(
                "created_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            updated_at_utc=data.get(
                "updated_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            is_focused=bool(data.get("is_focused", True)),
            metadata=data.get("metadata", {}),
        )


__all__ = ["Task"]
