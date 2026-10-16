"""ApprovalRequest and ApprovalStatus models.

Guarantees action-bound approvals: Approvals bind to the exact capability target
and arguments_hash, preventing replay attacks or action escalation post-approval.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from enum import Enum
import hashlib
import json
from typing import Any

from jarvis_agent.orchestration.models.risk import RiskAssessment


class ApprovalStatus(str, Enum):
    """Lifecycle status for an explicit operator approval request."""

    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Action-bound operator approval request for high-risk operations."""

    approval_id: str
    task_id: str
    node_id: str
    capability_target: str
    arguments_hash: str
    risk_assessment: RiskAssessment
    status: ApprovalStatus
    requested_at_utc: str
    expires_at_utc: str
    decided_at_utc: str | None = None
    decision_reason: str | None = None
    operator_id: str | None = None

    def is_expired(self, current_time_utc: datetime.datetime | None = None) -> bool:
        """Check if request has expired past its expiration timestamp."""
        now = current_time_utc or datetime.datetime.now(datetime.timezone.utc)
        exp = datetime.datetime.fromisoformat(self.expires_at_utc)
        return now >= exp

    def validate_arguments(self, raw_args: dict[str, Any]) -> bool:
        """Verify that arguments match the exact hash bound at approval request time."""
        canonical_json = json.dumps(raw_args, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()
        return digest.lower() == self.arguments_hash.lower()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["risk_assessment"] = self.risk_assessment.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ApprovalRequest:
        status = data["status"]
        if isinstance(status, str):
            status = ApprovalStatus(status)
        risk = data["risk_assessment"]
        if isinstance(risk, dict):
            risk = RiskAssessment.from_dict(risk)
        return cls(
            approval_id=data["approval_id"],
            task_id=data["task_id"],
            node_id=data["node_id"],
            capability_target=data["capability_target"],
            arguments_hash=data["arguments_hash"],
            risk_assessment=risk,
            status=status,
            requested_at_utc=data["requested_at_utc"],
            expires_at_utc=data["expires_at_utc"],
            decided_at_utc=data.get("decided_at_utc"),
            decision_reason=data.get("decision_reason"),
            operator_id=data.get("operator_id"),
        )


__all__ = ["ApprovalRequest", "ApprovalStatus"]
