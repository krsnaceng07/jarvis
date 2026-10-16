"""jarvis.agents.decision.decision_engine — Central decision and action controller.

OpenClaw parity: Implements the canonical decision-making lifecycle:
  INTENT → DECISION → ACTION → OBSERVATION → VERIFICATION → STATE → NEXT DECISION
Enforces strict execution bias, tool-loop intervention, and claim grounding.
"""

from __future__ import annotations

from typing import Any, Optional

from ..task.task_state import TaskStateManager
from .execution_planner import ExecutionPlanner, MultiStepPlan
from .intent import AnalyzedIntent, IntentClassifier
from .observation_normalizer import NormalizedObservation, ObservationNormalizer
from .tool_selection import ToolSelector
from .truthfulness import ClaimGroundingFilter, ClaimGroundingResult


class DecisionEngine:
    """Master decision-making and execution integrity engine for JARVIS."""

    def __init__(
        self,
        task_manager: Optional[TaskStateManager] = None,
        max_loop_threshold: int = 2,
    ) -> None:
        self.task_manager = task_manager or TaskStateManager.get_instance()
        self.tool_selector = ToolSelector(max_identical_calls=max_loop_threshold)
        self.execution_planner = ExecutionPlanner(tool_selector=self.tool_selector)

    def analyze_intent(self, text: str) -> AnalyzedIntent:
        """Analyzes user input for actionability, target entity, and required bias."""
        return IntentClassifier.classify(text)

    def prepare_plan(self, user_prompt: str, available_tools: set[str]) -> MultiStepPlan:
        """Decomposes the request into an executable multi-step plan."""
        plan = self.execution_planner.create_plan(user_prompt, available_tools)
        if plan.steps:
            self.task_manager.create_task(
                goal=user_prompt,
                steps=[s.description for s in plan.steps],
            )
        return plan

    def preflight_tool_execution(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Preflights tool arguments and checks for repetitive execution loops."""
        self.tool_selector.check_loop_intervention(tool_name, arguments)
        return self.tool_selector.preflight_arguments(tool_name, arguments)

    def reset(self) -> None:
        """Reset internal tool selector loop history."""
        self.tool_selector.reset()

    def process_tool_observation(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        raw_output: Any,
        error: Optional[Exception] = None,
        session_key: str = "agent:main:main",
    ) -> NormalizedObservation:
        """Normalizes output, verifies physical host state, and commits to task history."""
        obs = ObservationNormalizer.normalize(tool_name, arguments, raw_output, error)

        from ..verification.execution_verifier import VerificationOutcome

        verif = VerificationOutcome(
            status="verified" if obs.is_verified else "failed",
            verified=obs.is_verified,
            tool_name=tool_name,
            target_resource=str(
                obs.tangible_evidence.get("path") or obs.tangible_evidence.get("target") or ""
            ),
            error=obs.error_message,
        )

        affected = [obs.tangible_evidence["path"]] if "path" in obs.tangible_evidence else None

        self.task_manager.record_execution(
            tool_name=tool_name,
            arguments=arguments,
            raw_output=obs.raw_output or str(obs.error_message or ""),
            status=obs.status,
            verification=verif,
            affected_files=affected,
            session_key=session_key,
        )

        return obs

    def ground_response(
        self,
        assistant_text: str,
        recent_actions: Optional[list[dict[str, Any]]] = None,
    ) -> ClaimGroundingResult:
        """Validates assistant claims against real recorded evidence."""
        last_rec = self.task_manager.get_last_execution_record()
        return ClaimGroundingFilter.validate_and_ground(
            assistant_text=assistant_text,
            recent_actions=recent_actions,
            last_execution_record=last_rec,
        )
