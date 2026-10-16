"""jarvis.agents.decision.execution_planner — Multi-step task decomposition and replanning.

OpenClaw parity: Decomposes complex user requests into ordered tool steps
and supports dynamic replanning when intermediate steps fail or encounter barriers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .intent import IntentClassifier
from .tool_selection import ToolSelector


@dataclass(slots=True)
class PlanStep:
    step_index: int
    tool_name: str
    arguments: dict[str, Any]
    description: str
    expected_outcome: str
    status: str = "pending"  # "pending" | "executing" | "completed" | "failed"
    error: Optional[str] = None


@dataclass(slots=True)
class MultiStepPlan:
    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    status: str = "created"  # "created" | "executing" | "completed" | "failed"
    current_step_index: int = 1

    @property
    def current_step(self) -> Optional[PlanStep]:
        if 1 <= self.current_step_index <= len(self.steps):
            return self.steps[self.current_step_index - 1]
        return None

    @property
    def is_complete(self) -> bool:
        return all(s.status == "completed" for s in self.steps) if self.steps else False


class ExecutionPlanner:
    """Plans multi-step execution and adapts to runtime feedback."""

    def __init__(self, tool_selector: Optional[ToolSelector] = None) -> None:
        self.tool_selector = tool_selector or ToolSelector()

    def create_plan(self, user_prompt: str, available_tools: set[str]) -> MultiStepPlan:
        """Decomposes compound or single requests into an executable plan."""
        # Split on compound conjunctions (e.g. "and then", "and", "ani", "tespachi")
        sub_clauses = re.split(
            r"\b(?:and\s+then|and\s+also|\band\b|ani\s+tespachi|\bani\b)\b", user_prompt, flags=re.I
        )
        steps: list[PlanStep] = []

        step_num = 1
        for clause in sub_clauses:
            clause = clause.strip()
            if not clause:
                continue
            intent = IntentClassifier.classify(clause)
            if intent.is_actionable and intent.primary_tool in available_tools:
                plan_step = self.tool_selector.select_tool_for_intent(intent, available_tools)
                if plan_step:
                    steps.append(
                        PlanStep(
                            step_index=step_num,
                            tool_name=plan_step.tool_name,
                            arguments=plan_step.arguments,
                            description=clause,
                            expected_outcome=f"Successfully execute {plan_step.tool_name}",
                        )
                    )
                    step_num += 1

        # If compound splitting yielded nothing actionable, try whole prompt
        if not steps:
            intent = IntentClassifier.classify(user_prompt)
            if intent.is_actionable and intent.primary_tool in available_tools:
                plan_step = self.tool_selector.select_tool_for_intent(intent, available_tools)
                if plan_step:
                    steps.append(
                        PlanStep(
                            step_index=1,
                            tool_name=plan_step.tool_name,
                            arguments=plan_step.arguments,
                            description=user_prompt,
                            expected_outcome=f"Successfully execute {plan_step.tool_name}",
                        )
                    )

        return MultiStepPlan(
            goal=user_prompt,
            steps=steps,
            status="executing" if steps else "created",
        )

    def replan_on_failure(
        self,
        plan: MultiStepPlan,
        failed_step_index: int,
        error_message: str,
        available_tools: set[str],
    ) -> MultiStepPlan:
        """Dynamically adapts the plan when a step fails."""
        if not (1 <= failed_step_index <= len(plan.steps)):
            return plan

        failed_step = plan.steps[failed_step_index - 1]
        failed_step.status = "failed"
        failed_step.error = error_message

        # Identify potential fallback alternatives
        fallback_step: Optional[PlanStep] = None
        tool = failed_step.tool_name
        args = dict(failed_step.arguments)

        # Fallback 1: open_path -> exec start
        if tool == "open_path" and "exec" in available_tools:
            target = args.get("target", "")
            fallback_step = PlanStep(
                step_index=failed_step_index,
                tool_name="exec",
                arguments={"command": f"Start-Process '{target}'"},
                description=f"Fallback execution for opening '{target}'",
                expected_outcome=f"Process '{target}' launched via PowerShell",
            )
        # Fallback 2: remove_path -> exec Remove-Item
        elif tool == "remove_path" and "exec" in available_tools:
            path = args.get("path", "")
            fallback_step = PlanStep(
                step_index=failed_step_index,
                tool_name="exec",
                arguments={
                    "command": f"Remove-Item -Path '{path}' -Force -Recurse -ErrorAction SilentlyContinue"
                },
                description=f"Fallback removal for '{path}'",
                expected_outcome=f"Path '{path}' deleted via PowerShell",
            )
        # Fallback 3: process kill -> taskkill
        elif tool == "process" and args.get("action") == "kill" and "exec" in available_tools:
            proc = args.get("session_id", "")
            fallback_step = PlanStep(
                step_index=failed_step_index,
                tool_name="exec",
                arguments={"command": f"taskkill /F /IM {proc}*.exe"},
                description=f"Fallback force termination for '{proc}'",
                expected_outcome=f"Process '{proc}' terminated via taskkill",
            )

        if fallback_step:
            plan.steps[failed_step_index - 1] = fallback_step
            plan.current_step_index = failed_step_index
            plan.status = "executing"
        else:
            plan.status = "failed"

        return plan
