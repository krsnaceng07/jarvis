"""jarvis.agents.decision — Decision-making, intent understanding, tool selection, and truthfulness architecture.

OpenClaw parity package for autonomous decision lifecycles and physical groundings.
"""

from .decision_engine import DecisionEngine
from .execution_planner import ExecutionPlanner, MultiStepPlan, PlanStep
from .intent import AnalyzedIntent, IntentCategory, IntentClassifier
from .observation_normalizer import NormalizedObservation, ObservationNormalizer
from .provider_decision_adapter import (
    NormalizedFunctionCall,
    NormalizedFunctionResponse,
    ProviderDecisionAdapter,
)
from .tool_selection import ToolLoopInterventionError, ToolSelectionPlan, ToolSelector
from .truthfulness import ClaimGroundingFilter, ClaimGroundingResult

__all__ = [
    "DecisionEngine",
    "AnalyzedIntent",
    "IntentCategory",
    "IntentClassifier",
    "NormalizedObservation",
    "ObservationNormalizer",
    "ToolSelector",
    "ToolSelectionPlan",
    "ToolLoopInterventionError",
    "ExecutionPlanner",
    "MultiStepPlan",
    "PlanStep",
    "ClaimGroundingFilter",
    "ClaimGroundingResult",
    "ProviderDecisionAdapter",
    "NormalizedFunctionCall",
    "NormalizedFunctionResponse",
]
