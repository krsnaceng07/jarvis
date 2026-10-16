"""Ambiguity scoring engine for user turn intent and task binding."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from jarvis_agent.orchestration.models.user_turn import UserTurn
from jarvis_agent.orchestration.task.focus import TaskFocusManager


@dataclass(frozen=True, slots=True)
class AmbiguityAssessment:
    """Evaluation of ambiguity in binding an inbound turn to tasks."""

    ambiguity_score: float  # 0.0 (crisp) to 1.0 (highly ambiguous)
    is_ambiguous: bool
    reason: str
    candidate_task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AmbiguityScorer:
    """Evaluates task targeting ambiguity for inbound user turns."""

    def __init__(self, ambiguity_threshold: float = 0.6) -> None:
        self._threshold = ambiguity_threshold

    def evaluate(
        self,
        turn: UserTurn,
        active_task_ids: list[str],
        focus_manager: TaskFocusManager,
    ) -> AmbiguityAssessment:
        """Score the ambiguity of an incoming turn against active tasks."""
        text = turn.clean_text.strip()
        lower = text.lower()

        # Case 1: No active tasks -> Unambiguously a new task
        if not active_task_ids:
            return AmbiguityAssessment(
                ambiguity_score=0.0,
                is_ambiguous=False,
                reason="No active tasks in conversation; new task required.",
                candidate_task_ids=[],
            )

        # Case 2: Explicit new task indicators
        new_task_pattern = (
            r"^(new task|start a new task|forget that|instead,|another thing|also, please)\b"
        )
        if re.search(new_task_pattern, lower):
            return AmbiguityAssessment(
                ambiguity_score=0.1,
                is_ambiguous=False,
                reason="Explicit new task keyword detected.",
                candidate_task_ids=[],
            )

        # Case 3: Exactly 1 active task
        if len(active_task_ids) == 1:
            return AmbiguityAssessment(
                ambiguity_score=0.1,
                is_ambiguous=False,
                reason="Single active task in flight.",
                candidate_task_ids=list(active_task_ids),
            )

        # Case 4: Multiple active tasks
        # Check pronoun/antecedent resolution
        has_pronoun = bool(
            re.search(r"\b(it|that|this|them|the task|stop|pause|resume|cancel)\b", lower)
        )
        resolved_task, resolved_entity = focus_manager.resolve_antecedent(text)

        if has_pronoun and not resolved_entity and len(active_task_ids) > 1:
            # Ambiguous pronoun across multiple active tasks
            return AmbiguityAssessment(
                ambiguity_score=0.85,
                is_ambiguous=True,
                reason=f"Ambiguous reference '{text}' across {len(active_task_ids)} active tasks.",
                candidate_task_ids=list(active_task_ids),
            )

        # Default multi-task routing to current focus
        return AmbiguityAssessment(
            ambiguity_score=0.3,
            is_ambiguous=False,
            reason=f"Resolved to current focused task '{resolved_task}'.",
            candidate_task_ids=[resolved_task] if resolved_task else list(active_task_ids),
        )


__all__ = ["AmbiguityAssessment", "AmbiguityScorer"]
