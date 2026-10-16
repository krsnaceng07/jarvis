"""Error taxonomy package for Track 3.2 execution runtime."""

from jarvis_agent.execution.errors.taxonomy import (
    FAILURE_TO_ACTION_MAP,
    ActionRecommendation,
    ExecutionErrorDetail,
    ExecutionFailureClass,
)

__all__ = [
    "ActionRecommendation",
    "ExecutionErrorDetail",
    "ExecutionFailureClass",
    "FAILURE_TO_ACTION_MAP",
]
