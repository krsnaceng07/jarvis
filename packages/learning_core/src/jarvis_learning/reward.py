"""jarvis_learning.reward — configurable reward scoring.

Maps feedback signals and interaction outcomes to numerical reward
scores.  Weights are configurable so the operator can tune what
JARVIS prioritizes learning from.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RewardWeights:
    """Configurable weights for reward signal components."""

    explicit_success: float = 1.0
    verified_tool_success: float = 0.7
    accepted_answer: float = 0.5
    strategy_reuse_success: float = 0.3
    explicit_correction: float = -1.0
    task_failure: float = -0.8
    invalid_tool_call: float = -0.6
    unnecessary_repeat: float = -0.5
    hallucinated_capability: float = -0.5
    ignored_context: float = -0.4

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> RewardWeights:
        """Build from a config dict, using defaults for missing keys."""
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)


class RewardScorer:
    """Computes reward scores from feedback signals.

    The scorer maps named signals to their configured weight and
    sums them.  The result is clamped to ``[-2.0, 2.0]``.
    """

    def __init__(self, weights: RewardWeights | None = None) -> None:
        self.weights = weights or RewardWeights()
        self._weight_map: dict[str, float] = {
            name: getattr(self.weights, name) for name in self.weights.__dataclass_fields__
        }

    def score(self, signals: list[str]) -> float:
        """Sum the weights of the named signals, clamped to [-2, 2]."""
        total = 0.0
        for signal in signals:
            weight = self._weight_map.get(signal)
            if weight is not None:
                total += weight
            else:
                logger.debug("unknown reward signal ignored: %s", signal)
        return max(-2.0, min(2.0, total))

    def score_experience(
        self,
        *,
        success: bool,
        tool_succeeded: bool,
        user_feedback: str,
        verification_status: str,
        was_strategy_reuse: bool = False,
        had_unnecessary_steps: bool = False,
    ) -> float:
        """High-level scoring from experience attributes."""
        signals: list[str] = []

        if user_feedback in ("correction", "user_correction", "incorrect"):
            signals.append("explicit_correction")
        elif user_feedback in (
            "thumbs_up",
            "positive",
            "correct",
            "user_confirmed_success",
        ):
            signals.append("explicit_success")

        if success and tool_succeeded:
            signals.append("verified_tool_success")
        elif not success:
            signals.append("task_failure")

        if verification_status == "false_claim":
            signals.append("hallucinated_capability")

        if was_strategy_reuse and success:
            signals.append("strategy_reuse_success")

        if had_unnecessary_steps:
            signals.append("unnecessary_repeat")

        return self.score(signals)
