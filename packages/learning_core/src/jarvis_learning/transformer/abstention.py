"""Configurable Abstention and Out-Of-Distribution decision gates."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AbstentionConfig:
    """Configurable gates governing when local Transformer models must abstain."""

    min_calibrated_confidence: float = 0.80
    max_ood_score: float = 0.50
    min_class_support: int = 5
    require_calibration: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AbstentionConfig:
        return cls(
            min_calibrated_confidence=float(data.get("min_calibrated_confidence", 0.80)),
            max_ood_score=float(data.get("max_ood_score", 0.50)),
            min_class_support=int(data.get("min_class_support", 5)),
            require_calibration=bool(data.get("require_calibration", True)),
        )


@dataclass(frozen=True, slots=True)
class AbstentionDecision:
    """Decision output detailing whether model executed or safely abstained."""

    should_abstain: bool
    reason: str
    calibrated_confidence: float
    ood_score: float
    predicted_class: int | str
    metadata: dict[str, Any]
