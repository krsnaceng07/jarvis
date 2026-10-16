"""jarvis_learning.models.strategy_predictor — Model C: Strategy Predictor.

Estimates success probability of candidate strategies while explicitly
preventing selection bias (unselected strategies are never marked as failures).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifact import ModelArtifactBundle
from .base import LocalModel


@dataclass(frozen=True, slots=True)
class StrategyCandidateRecord:
    """Audit record capturing strategy candidate choice and observed outcome."""

    candidate_strategy_id: str
    candidate_rank: int
    selected: bool
    selection_reason: str  # "highest_confidence", "rule", "manual"
    observed_outcome: str  # "success", "failure", "unattempted"
    evaluated: bool


class StrategyPredictorModel(LocalModel):
    """Predicts likelihood of strategy success given task context."""

    def __init__(self, model_id: str = "strategy_predictor_local", version: str = "v001") -> None:
        super().__init__(target="strategy_predictor", model_id=model_id, version=version)

    def load(self, artifact_dir: Path) -> None:
        manifest, _, _, _, _ = ModelArtifactBundle.verify_and_load(
            artifact_dir, expected_target="strategy_predictor"
        )
        self.version = manifest.version
        self.model_id = manifest.model_id
        self._is_loaded = True

    def predict(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """Estimate success probability for a strategy."""
        candidates = input_data.get("candidate_strategies", [])
        results = []
        for strat in candidates:
            # Baseline probability derived from strategy reliability metrics
            success_count = strat.get("success_count", 0)
            failure_count = strat.get("failure_count", 0)
            total = success_count + failure_count
            p_success = (success_count / total) if total > 0 else 0.5
            results.append(
                {
                    "strategy_id": strat.get("id", ""),
                    "p_success": round(p_success, 3),
                }
            )
        results.sort(key=lambda x: x["p_success"], reverse=True)
        return {"predictions": results}

    def unload(self) -> None:
        self._is_loaded = False
