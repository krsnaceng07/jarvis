"""Structured BrainDecision taxonomy and decision envelope."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class BrainDecisionType(str, Enum):
    """Closed taxonomy of cognitive brain decisions."""

    PROPOSE_PLAN = "PROPOSE_PLAN"
    EXECUTE_NODE = "EXECUTE_NODE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    REQUEST_CLARIFICATION = "REQUEST_CLARIFICATION"
    RETRY_NODE = "RETRY_NODE"
    REPLAN = "REPLAN"
    COMPLETE_TASK = "COMPLETE_TASK"
    FAIL_TASK = "FAIL_TASK"
    NO_OP = "NO_OP"


@dataclass(frozen=True, slots=True)
class BrainDecision:
    """Authoritative cognitive decision emitted by the CognitiveBrain."""

    decision_type: BrainDecisionType
    task_id: str
    node_id: str | None = None
    confidence: float = 1.0  # Epistemic model confidence (NEVER grants authorization alone)
    is_authorized: bool = False  # Set strictly by DecisionPolicyGate
    reason: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["decision_type"] = self.decision_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrainDecision:
        dtype = data["decision_type"]
        if isinstance(dtype, str):
            dtype = BrainDecisionType(dtype)
        return cls(
            decision_type=dtype,
            task_id=data["task_id"],
            node_id=data.get("node_id"),
            confidence=float(data.get("confidence", 1.0)),
            is_authorized=bool(data.get("is_authorized", False)),
            reason=data.get("reason", ""),
            payload=data.get("payload", {}),
        )


__all__ = ["BrainDecision", "BrainDecisionType"]
