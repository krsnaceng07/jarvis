"""Immutable ExecutionCommand model with deterministic IdempotencyKey.

ExecutionCommands are the only authorized payloads handed across the scheduler
seam to downstream execution. They bind exact plan revisions, attempt counters,
and canonical arguments hashes to prevent replay, drift, or duplicate execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
import hashlib
import json
from typing import Any

from jarvis_agent.orchestration.models.risk import RiskAssessment


@dataclass(frozen=True, slots=True)
class ExecutionCommand:
    """Authorized, immutable command sent to downstream tool/system execution."""

    command_id: str
    task_id: str
    plan_id: str
    node_id: str
    execution_id: str
    attempt_id: int
    plan_revision: int
    capability_target: str
    arguments: dict[str, Any]
    arguments_hash: str
    idempotency_key: str
    issued_at_utc: str
    deadline_utc: str
    risk_assessment: RiskAssessment
    approval_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_assessment"] = self.risk_assessment.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionCommand:
        risk = data["risk_assessment"]
        if isinstance(risk, dict):
            risk = RiskAssessment.from_dict(risk)
        return cls(
            command_id=data["command_id"],
            task_id=data["task_id"],
            plan_id=data["plan_id"],
            node_id=data["node_id"],
            execution_id=data["execution_id"],
            attempt_id=int(data["attempt_id"]),
            plan_revision=int(data.get("plan_revision", 1)),
            capability_target=data["capability_target"],
            arguments=data["arguments"],
            arguments_hash=data["arguments_hash"],
            idempotency_key=data["idempotency_key"],
            issued_at_utc=data["issued_at_utc"],
            deadline_utc=data["deadline_utc"],
            risk_assessment=risk,
            approval_id=data.get("approval_id"),
        )

    @classmethod
    def create(
        cls,
        command_id: str,
        task_id: str,
        plan_id: str,
        node_id: str,
        execution_id: str,
        attempt_id: int,
        plan_revision: int,
        capability_target: str,
        arguments: dict[str, Any],
        deadline_utc: str,
        risk_assessment: RiskAssessment,
        approval_id: str | None = None,
        issued_at_utc: str | None = None,
    ) -> ExecutionCommand:
        """Create an ExecutionCommand, deterministically deriving hashes and idempotency key."""
        canonical_args = json.dumps(arguments, sort_keys=True, separators=(",", ":"))
        args_hash = hashlib.sha256(canonical_args.encode("utf-8")).hexdigest()

        idempotency_raw = f"{task_id}:{node_id}:{attempt_id}:{plan_revision}:{args_hash}"
        idempotency_key = hashlib.sha256(idempotency_raw.encode("utf-8")).hexdigest()

        now_utc = issued_at_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()

        return cls(
            command_id=command_id,
            task_id=task_id,
            plan_id=plan_id,
            node_id=node_id,
            execution_id=execution_id,
            attempt_id=attempt_id,
            plan_revision=plan_revision,
            capability_target=capability_target,
            arguments=arguments,
            arguments_hash=args_hash,
            idempotency_key=idempotency_key,
            issued_at_utc=now_utc,
            deadline_utc=deadline_utc,
            risk_assessment=risk_assessment,
            approval_id=approval_id,
        )


__all__ = ["ExecutionCommand"]
