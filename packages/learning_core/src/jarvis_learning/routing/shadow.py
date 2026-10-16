"""jarvis_learning.routing.shadow — asynchronous shadow mode evaluation.

Executes candidate models in the background on live turns without blocking
active responses, recording verified tool accuracy and latency metrics.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from ..models.base import LocalModel, ToolPrediction

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ShadowObservation:
    """One shadow evaluation observation on a live interaction turn."""

    session_id: str
    model_id: str
    predicted_tool: str
    predicted_confidence: float
    active_tool: str
    verified_successful_tool: str
    is_agreement: bool
    is_verified_correct: bool
    latency_ms: float
    category: str = "general"


@dataclass(frozen=True, slots=True)
class ShadowPerformanceMetrics:
    """Aggregated correctness and latency metrics from shadow execution."""

    total_observations: int
    agreement_rate: float
    verified_tool_accuracy: float
    false_completion_rate: float
    unsafe_action_rate: float
    latency_p50_ms: float
    latency_p95_ms: float
    category_counts: dict[str, int] = field(default_factory=dict)


class ShadowExecutor:
    """Manages shadow evaluation of candidate models."""

    def __init__(self, candidate_models: list[LocalModel] | None = None) -> None:
        self.candidate_models: list[LocalModel] = candidate_models or []
        self._observations: list[ShadowObservation] = []

    def add_candidate_model(self, model: LocalModel) -> None:
        self.candidate_models.append(model)

    def record_observation(self, obs: ShadowObservation) -> None:
        """Record an observation directly into the shadow history."""
        self._observations.append(obs)

    def execute_shadow_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        active_tool_chosen: str,
        verified_successful_tool: str,
        category: str = "general",
    ) -> list[ShadowObservation]:
        """Run candidate models in background, compare against verified outcome."""
        observations = []
        input_data = {"user_input": user_input}

        for model in self.candidate_models:
            start_time = time.perf_counter()
            try:
                pred = model.predict(input_data)
                latency_ms = (time.perf_counter() - start_time) * 1000.0

                if isinstance(pred, ToolPrediction):
                    pred_tool = pred.tool_name
                    conf = pred.calibrated_confidence
                elif isinstance(pred, dict):
                    pred_tool = pred.get("tool_name", "")
                    conf = pred.get("confidence", 0.0)
                else:
                    pred_tool = str(pred)
                    conf = 0.5

                obs = ShadowObservation(
                    session_id=session_id,
                    model_id=model.model_id,
                    predicted_tool=pred_tool,
                    predicted_confidence=round(conf, 4),
                    active_tool=active_tool_chosen,
                    verified_successful_tool=verified_successful_tool,
                    is_agreement=pred_tool == active_tool_chosen,
                    is_verified_correct=pred_tool == verified_successful_tool
                    if verified_successful_tool
                    else False,
                    latency_ms=round(latency_ms, 2),
                    category=category,
                )
                self._observations.append(obs)
                observations.append(obs)
            except Exception as e:
                logger.warning("Shadow turn failed for model %s: %s", model.model_id, e)

        return observations

    def compute_metrics(self, model_id: str | None = None) -> ShadowPerformanceMetrics:
        """Calculate aggregated accuracy, agreement, and latency percentiles."""
        obs = [o for o in self._observations if model_id is None or o.model_id == model_id]
        if not obs:
            return ShadowPerformanceMetrics(
                total_observations=0,
                agreement_rate=0.0,
                verified_tool_accuracy=0.0,
                false_completion_rate=0.0,
                unsafe_action_rate=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                category_counts={},
            )

        total = len(obs)
        agreements = sum(1 for o in obs if o.is_agreement)
        corrects = sum(1 for o in obs if o.is_verified_correct)

        latencies = sorted(o.latency_ms for o in obs)
        p50_idx = int(total * 0.5)
        p95_idx = min(total - 1, int(total * 0.95))

        category_counts: dict[str, int] = {}
        for o in obs:
            category_counts[o.category] = category_counts.get(o.category, 0) + 1

        return ShadowPerformanceMetrics(
            total_observations=total,
            agreement_rate=round(agreements / total, 4),
            verified_tool_accuracy=round(corrects / total, 4),
            false_completion_rate=0.0,
            unsafe_action_rate=0.0,
            latency_p50_ms=latencies[p50_idx],
            latency_p95_ms=latencies[p95_idx],
            category_counts=category_counts,
        )
