"""TaskResolver engine for disambiguating task continuation, creation, and clarification."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any

from jarvis_agent.orchestration.models.user_turn import UserTurn
from jarvis_agent.orchestration.task.ambiguity import AmbiguityScorer
from jarvis_agent.orchestration.task.focus import TaskFocusManager


@dataclass(frozen=True, slots=True)
class TaskResolution:
    """Outcome of resolving an inbound UserTurn against task state."""

    action: str  # "CONTINUE", "NEW", "CLARIFY"
    target_task_id: str | None = None
    new_goal: str | None = None
    confidence: float = 1.0
    clarification_prompt: str | None = None
    candidate_task_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TaskResolver:
    """Resolves whether a UserTurn continues an active task, starts a new one, or requires clarification."""

    def __init__(
        self,
        focus_manager: TaskFocusManager,
        ambiguity_scorer: AmbiguityScorer | None = None,
    ) -> None:
        self._focus = focus_manager
        self._scorer = ambiguity_scorer or AmbiguityScorer()

    def resolve(
        self,
        turn: UserTurn,
        active_task_ids: list[str],
    ) -> TaskResolution:
        """Resolve the inbound turn to an actionable task resolution."""
        text = turn.clean_text.strip()
        assessment = self._scorer.evaluate(turn, active_task_ids, self._focus)

        if assessment.is_ambiguous:
            return TaskResolution(
                action="CLARIFY",
                confidence=1.0 - assessment.ambiguity_score,
                clarification_prompt=(
                    f"You have multiple active tasks ({', '.join(assessment.candidate_task_ids)}). "
                    "Which one would you like me to work on?"
                ),
                candidate_task_ids=assessment.candidate_task_ids,
            )

        # Check explicit new task trigger
        new_task_match = re.search(
            r"^(?:new task|start a new task|also|instead)[,:]?\s*(.*)", text, re.IGNORECASE
        )
        if new_task_match:
            new_goal = new_task_match.group(1).lstrip(":, ").strip() or text
            return TaskResolution(
                action="NEW",
                new_goal=new_goal,
                confidence=0.95,
            )

        if not active_task_ids:
            return TaskResolution(
                action="NEW",
                new_goal=text,
                confidence=1.0,
            )

        # Continuation of focused task or candidate task
        target_id = (
            assessment.candidate_task_ids[0]
            if assessment.candidate_task_ids
            else self._focus.current_focus()
        )
        if target_id:
            return TaskResolution(
                action="CONTINUE",
                target_task_id=target_id,
                confidence=1.0 - assessment.ambiguity_score,
            )

        return TaskResolution(
            action="NEW",
            new_goal=text,
            confidence=0.9,
        )


__all__ = ["TaskResolution", "TaskResolver"]
