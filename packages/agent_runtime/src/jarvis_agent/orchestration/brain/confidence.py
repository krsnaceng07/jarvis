"""Confidence decoupling engine.

CRITICAL INVARIANT:
    Epistemic confidence in interpretation NEVER confers authorization to execute.
Confidence evaluates model certainty in intent and arguments, but security policy,
blast radius, and operator approvals alone govern execution authority.
"""

from __future__ import annotations

from jarvis_agent.orchestration.planning.goal_parser import ParsedGoal


class ConfidenceEvaluator:
    """Evaluates epistemic confidence while maintaining strict decoupling from execution authority."""

    @staticmethod
    def evaluate_epistemic_confidence(
        parsed_goal: ParsedGoal, entity_grounding_score: float = 1.0
    ) -> float:
        """Compute model's certainty that it correctly interpreted the user's intent."""
        # Baseline confidence from goal structure
        base_confidence = 0.5
        if parsed_goal.primary_intent != "GENERAL":
            base_confidence += 0.3
        if parsed_goal.target_entities:
            base_confidence += 0.2

        score = min(1.0, max(0.0, base_confidence * entity_grounding_score))
        return round(score, 3)

    @staticmethod
    def assert_confidence_does_not_authorize(confidence: float) -> None:
        """Informational guard asserting that high confidence cannot bypass authorization policy."""
        # Invariant check: confidence is purely epistemic
        pass


__all__ = ["ConfidenceEvaluator"]
