"""Machine-checkable ObservationRequirement and ObservationRecord models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class ObservationRequirement:
    """Specification of machine-checkable signals required from tool execution."""

    requirement_id: str
    predicate_type: str  # e.g. "FILE_EXISTS", "EXIT_CODE_ZERO", "JSON_MATCH", "DOM_VISIBLE"
    target: str  # Path, URL, CSS selector, command name, etc.
    expected_value: Any = None
    freshness_deadline_seconds: float = 300.0  # Max age of valid observation
    timeout_seconds: float = 60.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservationRequirement:
        return cls(
            requirement_id=data["requirement_id"],
            predicate_type=data["predicate_type"],
            target=data["target"],
            expected_value=data.get("expected_value"),
            freshness_deadline_seconds=float(data.get("freshness_deadline_seconds", 300.0)),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
        )


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    """Concrete empirical result captured from an execution attempt."""

    observation_id: str
    node_id: str
    captured_at_utc: str
    success: bool
    raw_data: Any
    evidence_ref: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObservationRecord:
        return cls(
            observation_id=data["observation_id"],
            node_id=data["node_id"],
            captured_at_utc=data.get(
                "captured_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            success=bool(data["success"]),
            raw_data=data.get("raw_data"),
            evidence_ref=data.get("evidence_ref"),
            error_message=data.get("error_message"),
            metadata=data.get("metadata", {}),
        )


__all__ = ["ObservationRecord", "ObservationRequirement"]
