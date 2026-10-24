"""Autonomous Claws & Background Worker Daemons Types — JARVIS Autonomous Architecture.

Defines the core data structures, enums, and results for Claws (autonomous
background worker agents) running in detached daemons without user intervention.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from typing import Any


class ClawJobStatus(str, Enum):
    """Lifecycle statuses for a scheduled or executing Claw job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    RETRYING = "RETRYING"


class ClawPriority(IntEnum):
    """Priority weights for autonomous worker jobs."""

    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


@dataclass(frozen=True, slots=True)
class ClawResult:
    """Execution result produced by an Autonomous Claw run."""

    success: bool
    output: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metrics": self.metrics,
        }


@dataclass(slots=True)
class ClawJob:
    """A persistent background job managed by the SQLite task queue."""

    job_id: str
    claw_id: str
    schedule: str | None = None
    priority: ClawPriority = ClawPriority.NORMAL
    status: ClawJobStatus = ClawJobStatus.PENDING
    payload: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 3
    last_error: str | None = None
    result: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    scheduled_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "claw_id": self.claw_id,
            "schedule": self.schedule,
            "priority": self.priority.value,
            "status": self.status.value,
            "payload": self.payload,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "last_error": self.last_error,
            "result": self.result,
            "created_at": self.created_at,
            "scheduled_at": self.scheduled_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> ClawJob:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        result = row.get("result")
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except Exception:
                result = None

        return cls(
            job_id=row["job_id"],
            claw_id=row["claw_id"],
            schedule=row.get("schedule"),
            priority=ClawPriority(row.get("priority", 5)),
            status=ClawJobStatus(row.get("status", "PENDING")),
            payload=payload or {},
            attempts=int(row.get("attempts", 0)),
            max_attempts=int(row.get("max_attempts", 3)),
            last_error=row.get("last_error"),
            result=result,
            created_at=row.get("created_at") or datetime.now(timezone.utc).isoformat(),
            scheduled_at=row.get("scheduled_at"),
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
        )


__all__ = [
    "ClawJob",
    "ClawJobStatus",
    "ClawPriority",
    "ClawResult",
]
