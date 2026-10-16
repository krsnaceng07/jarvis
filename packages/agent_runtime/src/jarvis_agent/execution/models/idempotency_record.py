"""IdempotencyRecord and IdempotencyState models for Track 3.2.

Provides persistent idempotency tracking for command execution across process
restarts to prevent duplicate side-effect execution and verify idempotent replay.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
import enum
from typing import Any


class IdempotencyState(enum.Enum):
    """Execution lifecycle state stored in the idempotency ledger."""

    NEVER_SEEN = "NEVER_SEEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Record tracking an individual command execution attempt by idempotency key."""

    idempotency_key: str
    task_id: str
    plan_id: str
    plan_revision: int
    node_id: str
    attempt_id: int
    command_id: str
    arguments_hash: str
    capability_target: str
    state: IdempotencyState
    created_at_utc: str
    updated_at_utc: str
    execution_result: dict[str, Any] | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize record to dictionary."""
        d = asdict(self)
        d["state"] = self.state.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> IdempotencyRecord:
        """Deserialize record from dictionary."""
        st = data["state"]
        state = IdempotencyState(st) if isinstance(st, str) else st
        return cls(
            idempotency_key=data["idempotency_key"],
            task_id=data["task_id"],
            plan_id=data["plan_id"],
            plan_revision=int(data.get("plan_revision", 1)),
            node_id=data["node_id"],
            attempt_id=int(data.get("attempt_id", 1)),
            command_id=data["command_id"],
            arguments_hash=data["arguments_hash"],
            capability_target=data["capability_target"],
            state=state,
            created_at_utc=data["created_at_utc"],
            updated_at_utc=data["updated_at_utc"],
            execution_result=data.get("execution_result"),
            error_message=data.get("error_message"),
        )

    @classmethod
    def create_new(
        cls,
        idempotency_key: str,
        task_id: str,
        plan_id: str,
        plan_revision: int,
        node_id: str,
        attempt_id: int,
        command_id: str,
        arguments_hash: str,
        capability_target: str,
        state: IdempotencyState = IdempotencyState.IN_PROGRESS,
    ) -> IdempotencyRecord:
        """Create a new initial record."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return cls(
            idempotency_key=idempotency_key,
            task_id=task_id,
            plan_id=plan_id,
            plan_revision=plan_revision,
            node_id=node_id,
            attempt_id=attempt_id,
            command_id=command_id,
            arguments_hash=arguments_hash,
            capability_target=capability_target,
            state=state,
            created_at_utc=now,
            updated_at_utc=now,
        )


__all__ = ["IdempotencyRecord", "IdempotencyState"]
