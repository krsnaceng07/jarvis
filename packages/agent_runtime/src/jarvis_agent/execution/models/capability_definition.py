"""CapabilityDefinition and SideEffectClass models for Track 3.2.

Defines registered tool capabilities, their JSON schemas, risk categories,
required permissions, sandbox tiers, side-effect classifications, and execution timeouts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import enum
from typing import Any

from jarvis_agent.orchestration.models.risk import RiskClass


class SideEffectClass(enum.Enum):
    """Categorization of side-effects caused by tool execution."""

    READ_ONLY = "READ_ONLY"
    IDEMPOTENT_MUTATION = "IDEMPOTENT_MUTATION"
    NON_IDEMPOTENT_MUTATION = "NON_IDEMPOTENT_MUTATION"
    EXTERNAL_TRANSACTION = "EXTERNAL_TRANSACTION"


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """Specification of an authorized capability executable by Track 3.2 runtime."""

    capability_id: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_class: RiskClass
    required_permissions: list[str] = field(default_factory=list)
    sandbox_tier_required: str = "TIER_0_APP"
    side_effect_class: SideEffectClass = SideEffectClass.READ_ONLY
    timeout_seconds: float = 60.0
    supports_cancellation: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize capability definition to dictionary."""
        d = asdict(self)
        d["risk_class"] = self.risk_class.value
        d["side_effect_class"] = self.side_effect_class.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityDefinition:
        """Deserialize capability definition from dictionary."""
        risk_val = data["risk_class"]
        risk_class = RiskClass(risk_val) if isinstance(risk_val, str) else risk_val

        side_val = data.get("side_effect_class", "READ_ONLY")
        side_effect = SideEffectClass(side_val) if isinstance(side_val, str) else side_val

        return cls(
            capability_id=data["capability_id"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            risk_class=risk_class,
            required_permissions=list(data.get("required_permissions", [])),
            sandbox_tier_required=data.get("sandbox_tier_required", "TIER_0_APP"),
            side_effect_class=side_effect,
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            supports_cancellation=bool(data.get("supports_cancellation", True)),
        )


__all__ = ["CapabilityDefinition", "SideEffectClass"]
