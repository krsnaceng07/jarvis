"""jarvis_learning.models.decision_trace — explainability and decision logging.

Every routing decision (whether dispatched to the local model, strategy
store, or foundation model) generates a diagnostic trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..experience import generate_id, now_ms


@dataclass(frozen=True, slots=True)
class DecisionTrace:
    """Complete diagnostic record of a routing decision."""

    trace_id: str
    timestamp: int
    session_id: str
    user_input: str
    selected_handler: str  # "strategy_store" | "local_model" | "foundation_llm"
    routing_state: str = "NO_MODEL"  # From RoutingState enum
    task_family: str = "tool_policy"
    model_id: str = ""
    model_version: str = ""
    model_availability: str = (
        "none"  # "active" | "shadow" | "unavailable" | "incompatible" | "none"
    )
    raw_confidence: float = 0.0
    calibrated_confidence: float = 0.0
    ood_score: float = 0.0
    calibration_state: str = (
        "unavailable"  # "calibrated" | "uncalibrated" | "stale" | "unavailable"
    )
    risk_level: str = "low"
    eligibility_result: str = "ineligible"  # "eligible" | "ineligible" | "abstained"
    authorization_result: str = (
        "denied"  # "authorized" | "denied" | "advisory_only" | "shadow_only"
    )
    policy_result: str = (
        "allowed"  # "allowed" | "blocked_destructive" | "blocked_risk" | "blocked_whitelist"
    )
    guard_decision: str = (
        "allowed"  # "allowed" | "blocked_safety" | "blocked_ood" | "blocked_uncalibrated"
    )
    fallback_reason: str = ""
    tool_predicted: str = ""
    tool_executed: str = ""
    final_route: str = "foundation_llm"
    verification_status: str = ""
    latency_ms: float = 0.0
    evidence_manifest_hash: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "user_input": self.user_input,
            "selected_handler": self.selected_handler,
            "routing_state": self.routing_state,
            "task_family": self.task_family,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "model_availability": self.model_availability,
            "raw_confidence": self.raw_confidence,
            "calibrated_confidence": self.calibrated_confidence,
            "ood_score": self.ood_score,
            "calibration_state": self.calibration_state,
            "risk_level": self.risk_level,
            "eligibility_result": self.eligibility_result,
            "authorization_result": self.authorization_result,
            "policy_result": self.policy_result,
            "guard_decision": self.guard_decision,
            "fallback_reason": self.fallback_reason,
            "tool_predicted": self.tool_predicted,
            "tool_executed": self.tool_executed,
            "final_route": self.final_route,
            "verification_status": self.verification_status,
            "latency_ms": self.latency_ms,
            "evidence_manifest_hash": self.evidence_manifest_hash,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DecisionTrace:
        return cls(
            trace_id=d["trace_id"],
            timestamp=int(d["timestamp"]),
            session_id=d.get("session_id", ""),
            user_input=d.get("user_input", ""),
            selected_handler=d.get("selected_handler", "foundation_llm"),
            routing_state=d.get("routing_state", "NO_MODEL"),
            task_family=d.get("task_family", "tool_policy"),
            model_id=d.get("model_id", ""),
            model_version=d.get("model_version", ""),
            model_availability=d.get("model_availability", "none"),
            raw_confidence=float(d.get("raw_confidence", 0.0)),
            calibrated_confidence=float(d.get("calibrated_confidence", 0.0)),
            ood_score=float(d.get("ood_score", 0.0)),
            calibration_state=d.get("calibration_state", "unavailable"),
            risk_level=d.get("risk_level", "low"),
            eligibility_result=d.get("eligibility_result", "ineligible"),
            authorization_result=d.get("authorization_result", "denied"),
            policy_result=d.get("policy_result", "allowed"),
            guard_decision=d.get("guard_decision", "allowed"),
            fallback_reason=d.get("fallback_reason", ""),
            tool_predicted=d.get("tool_predicted", ""),
            tool_executed=d.get("tool_executed", ""),
            final_route=d.get("final_route", d.get("selected_handler", "foundation_llm")),
            verification_status=d.get("verification_status", ""),
            latency_ms=float(d.get("latency_ms", 0.0)),
            evidence_manifest_hash=d.get("evidence_manifest_hash", ""),
            metadata=d.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        user_input: str,
        selected_handler: str,
        **kwargs: Any,
    ) -> DecisionTrace:
        if "final_route" not in kwargs:
            kwargs["final_route"] = selected_handler
        return cls(
            trace_id=generate_id(),
            timestamp=now_ms(),
            session_id=session_id,
            user_input=user_input,
            selected_handler=selected_handler,
            **kwargs,
        )
