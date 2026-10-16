"""PlanNode and NodeStatus models representing discrete steps in a PlanDAG."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from enum import Enum
from typing import Any

from jarvis_agent.orchestration.models.observation import ObservationRequirement
from jarvis_agent.orchestration.models.risk import RiskAssessment
from jarvis_agent.orchestration.models.verification import VerificationRequirement


class NodeStatus(str, Enum):
    """Lifecycle status of an individual execution node within a PlanDAG."""

    PENDING = "PENDING"
    READY = "READY"
    RUNNING = "RUNNING"
    WAITING_FOR_TOOL = "WAITING_FOR_TOOL"
    WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SKIPPED = "SKIPPED"
    AMBIGUOUS_CRASH_SUSPECT = "AMBIGUOUS_CRASH_SUSPECT"

    @property
    def is_terminal(self) -> bool:
        return self in (
            NodeStatus.COMPLETED,
            NodeStatus.FAILED,
            NodeStatus.CANCELLED,
            NodeStatus.SKIPPED,
        )

    @property
    def is_in_flight(self) -> bool:
        return self in (
            NodeStatus.RUNNING,
            NodeStatus.WAITING_FOR_TOOL,
            NodeStatus.VERIFYING,
            NodeStatus.AMBIGUOUS_CRASH_SUSPECT,
        )


@dataclass(frozen=True, slots=True)
class PlanNode:
    """Discrete execution step within an immutable PlanDAG."""

    node_id: str
    plan_id: str
    goal: str
    capability: str
    arguments: dict[str, Any]
    dependencies: list[str]  # Node IDs that must COMPLETE before this node is READY
    status: NodeStatus
    risk_assessment: RiskAssessment
    observation_requirements: list[ObservationRequirement] = field(default_factory=list)
    verification_requirements: list[VerificationRequirement] = field(default_factory=list)
    max_attempts: int = 3
    current_attempt: int = 0
    execution_id: str | None = None
    timeout_seconds: float = 120.0
    created_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    started_at_utc: str | None = None
    completed_at_utc: str | None = None
    last_observation_ref: str | None = None
    last_verification_ref: str | None = None
    error_message: str | None = None

    def can_retry(self) -> bool:
        """Check whether node has remaining retry attempts."""
        return self.current_attempt < self.max_attempts and self.status == NodeStatus.FAILED

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["risk_assessment"] = self.risk_assessment.to_dict()
        d["observation_requirements"] = [o.to_dict() for o in self.observation_requirements]
        d["verification_requirements"] = [v.to_dict() for v in self.verification_requirements]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanNode:
        status = data["status"]
        if isinstance(status, str):
            status = NodeStatus(status)
        risk = data["risk_assessment"]
        if isinstance(risk, dict):
            risk = RiskAssessment.from_dict(risk)
        obs = [
            ObservationRequirement.from_dict(o) if isinstance(o, dict) else o
            for o in data.get("observation_requirements", [])
        ]
        ver = [
            VerificationRequirement.from_dict(v) if isinstance(v, dict) else v
            for v in data.get("verification_requirements", [])
        ]
        return cls(
            node_id=data["node_id"],
            plan_id=data["plan_id"],
            goal=data["goal"],
            capability=data["capability"],
            arguments=data.get("arguments", {}),
            dependencies=list(data.get("dependencies", [])),
            status=status,
            risk_assessment=risk,
            observation_requirements=obs,
            verification_requirements=ver,
            max_attempts=int(data.get("max_attempts", 3)),
            current_attempt=int(data.get("current_attempt", 0)),
            execution_id=data.get("execution_id"),
            timeout_seconds=float(data.get("timeout_seconds", 120.0)),
            created_at_utc=data.get(
                "created_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            started_at_utc=data.get("started_at_utc"),
            completed_at_utc=data.get("completed_at_utc"),
            last_observation_ref=data.get("last_observation_ref"),
            last_verification_ref=data.get("last_verification_ref"),
            error_message=data.get("error_message"),
        )


__all__ = ["NodeStatus", "PlanNode"]
