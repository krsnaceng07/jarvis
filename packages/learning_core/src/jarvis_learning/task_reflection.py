"""Multi-Step Task Episode Reflection.

Reflects across multi-step episodes rather than single isolated tool calls:
- Detects partial progress vs total failure
- Pinpoints the critical failure or bottleneck step
- Identifies dead-ends and cyclic loops
- Extracts clean sub-sequences worthy of learning
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class TaskStepRecord:
    step_index: int
    tool_name: str
    args: Dict[str, Any]
    success: bool
    error: Optional[str] = None
    duration_ms: float = 0.0
    verified: bool = False


@dataclass(slots=True)
class TaskEpisodeReflection:
    task_id: str
    total_steps: int
    successful_steps: int
    overall_outcome: str  # "FULL_SUCCESS", "PARTIAL_SUCCESS", "TOTAL_FAILURE"
    critical_failure_step: Optional[int] = None
    bottleneck_tool: Optional[str] = None
    cyclic_steps_count: int = 0
    extractable_subsequences: List[List[str]] = field(default_factory=list)


class TaskEpisodeReflector:
    """Analyzes a multi-step execution episode."""

    @classmethod
    def reflect_episode(cls, task_id: str, steps: List[TaskStepRecord]) -> TaskEpisodeReflection:
        if not steps:
            return TaskEpisodeReflection(
                task_id=task_id,
                total_steps=0,
                successful_steps=0,
                overall_outcome="TOTAL_FAILURE",
            )

        total = len(steps)
        successes = sum(1 for s in steps if s.success and s.verified)

        # Check cyclic steps (same tool called consecutively with identical args)
        cyclic_count = 0
        for i in range(1, total):
            if steps[i].tool_name == steps[i - 1].tool_name and steps[i].args == steps[i - 1].args:
                cyclic_count += 1

        # Find first critical failure step
        critical_step: Optional[int] = None
        bottleneck: Optional[str] = None
        for s in steps:
            if not s.success or not s.verified:
                critical_step = s.step_index
                bottleneck = s.tool_name
                break

        # Classify overall outcome
        if steps[-1].success and steps[-1].verified:
            if successes == total:
                outcome = "FULL_SUCCESS"
            else:
                outcome = "PARTIAL_SUCCESS"  # Succeeded eventually despite prior failures
        else:
            outcome = "TOTAL_FAILURE"

        # Extract successful contiguous subsequences of length >= 2
        subseqs: List[List[str]] = []
        curr: List[str] = []
        for s in steps:
            if s.success and s.verified:
                curr.append(s.tool_name)
            else:
                if len(curr) >= 2:
                    subseqs.append(list(curr))
                curr = []
        if len(curr) >= 2:
            subseqs.append(list(curr))

        return TaskEpisodeReflection(
            task_id=task_id,
            total_steps=total,
            successful_steps=successes,
            overall_outcome=outcome,
            critical_failure_step=critical_step,
            bottleneck_tool=bottleneck,
            cyclic_steps_count=cyclic_count,
            extractable_subsequences=subseqs,
        )
