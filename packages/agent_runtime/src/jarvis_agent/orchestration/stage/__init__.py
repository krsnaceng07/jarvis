"""Stage detection, legal transition matrix, and stage machine oracle."""

from __future__ import annotations

from jarvis_agent.orchestration.stage.detector import (
    StageDetectionResult,
    StageDetector,
)
from jarvis_agent.orchestration.stage.oracle import StageReferenceOracle
from jarvis_agent.orchestration.stage.transition import StageTransitionEngine
from jarvis_agent.orchestration.stage.transition_rules import (
    LEGAL_TRANSITIONS,
    IllegalStageTransitionError,
    is_transition_legal,
    validate_transition,
)

__all__ = [
    "LEGAL_TRANSITIONS",
    "IllegalStageTransitionError",
    "StageDetectionResult",
    "StageDetector",
    "StageReferenceOracle",
    "StageTransitionEngine",
    "is_transition_legal",
    "validate_transition",
]
