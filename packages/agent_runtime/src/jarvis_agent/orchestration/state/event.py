"""DomainEvent and EventType definitions for the orchestration event store."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from enum import Enum
from typing import Any
import uuid


class EventType(str, Enum):
    """Closed enumeration of orchestration domain events."""

    TASK_CREATED = "TASK_CREATED"
    STAGE_CHANGED = "STAGE_CHANGED"
    PLAN_CREATED = "PLAN_CREATED"
    PLAN_REVISED = "PLAN_REVISED"
    NODE_READY = "NODE_READY"
    NODE_STARTED = "NODE_STARTED"
    NODE_OBSERVED = "NODE_OBSERVED"
    NODE_VERIFIED = "NODE_VERIFIED"
    NODE_FAILED = "NODE_FAILED"
    NODE_RETRY_SCHEDULED = "NODE_RETRY_SCHEDULED"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED"
    APPROVAL_GRANTED = "APPROVAL_GRANTED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    TASK_PAUSED = "TASK_PAUSED"
    TASK_RESUMED = "TASK_RESUMED"
    TASK_CANCELLED = "TASK_CANCELLED"
    TASK_COMPLETED = "TASK_COMPLETED"
    AMBIGUOUS_CRASH_SUSPECTED = "AMBIGUOUS_CRASH_SUSPECTED"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Immutable domain event recorded in the append-only event journal."""

    event_id: str
    task_id: str
    conversation_id: str
    event_type: EventType
    timestamp_utc: str
    payload: dict[str, Any]
    sequence_number: int
    causation_event_id: str | None = None
    correlation_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DomainEvent:
        evt_type = data["event_type"]
        if isinstance(evt_type, str):
            evt_type = EventType(evt_type)
        return cls(
            event_id=data["event_id"],
            task_id=data["task_id"],
            conversation_id=data["conversation_id"],
            event_type=evt_type,
            timestamp_utc=data["timestamp_utc"],
            payload=data.get("payload", {}),
            sequence_number=int(data["sequence_number"]),
            causation_event_id=data.get("causation_event_id"),
            correlation_id=data.get("correlation_id", ""),
        )

    @classmethod
    def create(
        cls,
        task_id: str,
        conversation_id: str,
        event_type: EventType,
        payload: dict[str, Any],
        sequence_number: int,
        event_id: str | None = None,
        causation_event_id: str | None = None,
        correlation_id: str = "",
        timestamp_utc: str | None = None,
    ) -> DomainEvent:
        """Convenience factory for creating a domain event."""
        eid = event_id or f"evt_{uuid.uuid4().hex[:12]}"
        ts = timestamp_utc or datetime.datetime.now(datetime.timezone.utc).isoformat()
        return cls(
            event_id=eid,
            task_id=task_id,
            conversation_id=conversation_id,
            event_type=event_type,
            timestamp_utc=ts,
            payload=payload,
            sequence_number=sequence_number,
            causation_event_id=causation_event_id,
            correlation_id=correlation_id,
        )


__all__ = ["DomainEvent", "EventType"]
