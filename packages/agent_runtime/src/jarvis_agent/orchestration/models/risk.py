"""Multi-dimensional RiskAssessment and derived RiskClass taxonomy.

Governs execution safety policies, ensuring actions are authorized according
to risk classification, reversibility, and blast radius rather than epistemic confidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class RiskClass(str, Enum):
    """Categorical risk class for tasks and execution commands."""

    READ_ONLY = "READ_ONLY"  # No side effects, purely observational or read query
    LOW = "LOW"  # Local isolated mutations (e.g. temp scratchpad)
    MEDIUM = "MEDIUM"  # Local project edits (reversible via version control)
    HIGH = "HIGH"  # Destructive local changes or external service mutations
    CRITICAL = (
        "CRITICAL"  # System-level modifications, credential access, or irreversible data loss
    )

    @property
    def requires_approval_by_default(self) -> bool:
        """High and Critical risk operations mandate explicit operator approval by default."""
        return self in (RiskClass.HIGH, RiskClass.CRITICAL)


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    """Multi-dimensional risk evaluation for a node, plan, or command."""

    risk_class: RiskClass
    blast_radius: str  # e.g. "LOCAL_TEMP", "LOCAL_PROJECT", "HOST_FS", "EXTERNAL_NETWORK"
    reversibility: str  # e.g. "FULLY_REVERSIBLE", "COMPENSATION_POSSIBLE", "IRREVERSIBLE"
    data_sensitivity: str  # e.g. "PUBLIC", "INTERNAL", "CONFIDENTIAL", "CREDENTIALS"
    external_effect: str  # e.g. "NONE", "IDEMPOTENT_READ", "EXTERNAL_MUTATION"
    requires_operator_approval: bool
    justification: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["risk_class"] = self.risk_class.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RiskAssessment:
        risk_class = data["risk_class"]
        if isinstance(risk_class, str):
            risk_class = RiskClass(risk_class)
        return cls(
            risk_class=risk_class,
            blast_radius=data.get("blast_radius", "LOCAL_PROJECT"),
            reversibility=data.get("reversibility", "COMPENSATION_POSSIBLE"),
            data_sensitivity=data.get("data_sensitivity", "INTERNAL"),
            external_effect=data.get("external_effect", "NONE"),
            requires_operator_approval=data.get(
                "requires_operator_approval", risk_class.requires_approval_by_default
            ),
            justification=data.get("justification", ""),
        )

    @classmethod
    def safe_read_only(cls, justification: str = "Read-only inspection") -> RiskAssessment:
        """Convenience constructor for read-only actions."""
        return cls(
            risk_class=RiskClass.READ_ONLY,
            blast_radius="NONE",
            reversibility="FULLY_REVERSIBLE",
            data_sensitivity="INTERNAL",
            external_effect="NONE",
            requires_operator_approval=False,
            justification=justification,
        )


__all__ = ["RiskAssessment", "RiskClass"]
