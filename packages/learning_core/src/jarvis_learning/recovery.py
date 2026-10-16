from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RecoveryPlan:
    trigger_failure_type: Any
    max_attempts: int = 1
    retry_policy: Literal[
        "immediate",
        "backoff",
        "probe_first",
        "switch_target",
        "narrow_query",
        "user_confirm",
        "stop",
    ] = "probe_first"
    argument_mutation_policy: Literal["none", "switch_target", "narrow_query"] = "none"
    allowed_alternatives: tuple[str, ...] = ()
    requires_confirmation: bool = False
    reset_stage: bool = False
    verification_requirement: str = "physical_readback"
    stop_conditions: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger_failure_type": str(
                getattr(self.trigger_failure_type, "value", self.trigger_failure_type)
            ),
            "max_attempts": self.max_attempts,
            "retry_policy": self.retry_policy,
            "argument_mutation_policy": self.argument_mutation_policy,
            "allowed_alternatives": list(self.allowed_alternatives),
            "requires_confirmation": self.requires_confirmation,
            "reset_stage": self.reset_stage,
            "verification_requirement": self.verification_requirement,
            "stop_conditions": list(self.stop_conditions),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecoveryPlan:
        return cls(
            trigger_failure_type=data.get("trigger_failure_type", "unknown"),
            max_attempts=int(data.get("max_attempts", 1)),
            retry_policy=data.get("retry_policy", "probe_first"),
            argument_mutation_policy=data.get("argument_mutation_policy", "none"),
            allowed_alternatives=tuple(data.get("allowed_alternatives", [])),
            requires_confirmation=bool(data.get("requires_confirmation", False)),
            reset_stage=bool(data.get("reset_stage", False)),
            verification_requirement=str(data.get("verification_requirement", "physical_readback")),
            stop_conditions=tuple(data.get("stop_conditions", [])),
        )
