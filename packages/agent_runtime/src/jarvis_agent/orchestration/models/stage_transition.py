"""Immutable StageTransition record with reason codes and evidence provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any

from jarvis_agent.orchestration.models.stage import TaskStage


@dataclass(frozen=True, slots=True)
class StageTransition:
    """Audit record representing an authoritative stage transition."""

    transition_id: str
    task_id: str
    previous_stage: TaskStage
    new_stage: TaskStage
    reason_codes: list[str]
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)
    timestamp_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    initiator: str = "STAGE_DETECTOR"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["previous_stage"] = self.previous_stage.value
        d["new_stage"] = self.new_stage.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageTransition:
        prev_stage = data["previous_stage"]
        if isinstance(prev_stage, str):
            prev_stage = TaskStage(prev_stage)
        new_stage = data["new_stage"]
        if isinstance(new_stage, str):
            new_stage = TaskStage(new_stage)
        return cls(
            transition_id=data["transition_id"],
            task_id=data["task_id"],
            previous_stage=prev_stage,
            new_stage=new_stage,
            reason_codes=list(data.get("reason_codes", [])),
            confidence=float(data.get("confidence", 1.0)),
            evidence_refs=list(data.get("evidence_refs", [])),
            timestamp_utc=data.get(
                "timestamp_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            initiator=data.get("initiator", "STAGE_DETECTOR"),
        )


__all__ = ["StageTransition"]
