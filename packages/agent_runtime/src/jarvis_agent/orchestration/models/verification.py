"""VerificationRequirement and VerificationResult models.

Decouples execution observation from completion verification. A node or task
is NEVER completed purely because a tool returns or a model claims completion;
all mandatory VerificationRequirements must evaluate to true.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class VerificationAssertion:
    """Individual assertion within a verification check."""

    assertion_id: str
    field_name: str
    assertion_type: str  # e.g. "EQUALS", "CONTAINS", "NON_EMPTY", "SCHEMA_VALID", "EXIT_CODE_ZERO"
    expected_value: Any

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationAssertion:
        return cls(
            assertion_id=data["assertion_id"],
            field_name=data["field_name"],
            assertion_type=data["assertion_type"],
            expected_value=data.get("expected_value"),
        )


@dataclass(frozen=True, slots=True)
class VerificationRequirement:
    """Specification of mandatory verification assertions for a plan node or task."""

    verification_id: str
    node_id: str
    assertions: list[VerificationAssertion]
    mandatory: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["assertions"] = [a.to_dict() for a in self.assertions]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationRequirement:
        assertions = [
            VerificationAssertion.from_dict(a) if isinstance(a, dict) else a
            for a in data.get("assertions", [])
        ]
        return cls(
            verification_id=data["verification_id"],
            node_id=data["node_id"],
            assertions=assertions,
            mandatory=bool(data.get("mandatory", True)),
        )


@dataclass(frozen=True, slots=True)
class VerificationResult:
    """Authoritative result of evaluating verification assertions."""

    result_id: str
    verification_id: str
    node_id: str
    passed: bool
    assertions_evaluated: int
    assertions_passed: int
    diffs: dict[str, Any] = field(default_factory=dict)
    evidence_refs: list[str] = field(default_factory=list)
    evaluated_at_utc: str = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VerificationResult:
        return cls(
            result_id=data["result_id"],
            verification_id=data["verification_id"],
            node_id=data["node_id"],
            passed=bool(data["passed"]),
            assertions_evaluated=int(data.get("assertions_evaluated", 0)),
            assertions_passed=int(data.get("assertions_passed", 0)),
            diffs=data.get("diffs", {}),
            evidence_refs=list(data.get("evidence_refs", [])),
            evaluated_at_utc=data.get(
                "evaluated_at_utc", datetime.datetime.now(datetime.timezone.utc).isoformat()
            ),
            error_message=data.get("error_message"),
        )


__all__ = ["VerificationAssertion", "VerificationRequirement", "VerificationResult"]
