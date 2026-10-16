"""jarvis_learning.lineage — Provenance tracking, causal adoption traces, and task isolation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, ClassVar


class VerificationOutcome(str, Enum):
    """Rigorous verification states distinguishing true success from verifier failure."""

    VERIFIED_SUCCESS = "VERIFIED_SUCCESS"
    VERIFIED_FAILURE = "VERIFIED_FAILURE"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    UNVERIFIED = "UNVERIFIED"
    VERIFIER_ERROR = "VERIFIER_ERROR"
    ENVIRONMENT_UNKNOWN = "ENVIRONMENT_UNKNOWN"


@dataclass(frozen=True, slots=True)
class TaskIsolationContext:
    """Explicit hierarchy and isolation for parallel agents, turns, and attempts."""

    session_id: str
    turn_id: str
    agent_id: str = "main"
    parent_task_id: str | None = None
    root_task_id: str | None = None
    attempt_id: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class StrategyLineage:
    """Unbroken provenance chain tying a learned strategy to verified source experiences."""

    strategy_id: str
    origin: str  # Must be "reflection"
    source_experience_ids: tuple[str, ...] = ()
    source_session_ids: tuple[str, ...] = ()
    created_by: str = "learning_pipeline"
    manual_override: bool = False  # Strictly False in automated learning
    verified: bool = True
    created_at_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyLineage:
        return cls(
            strategy_id=str(data["strategy_id"]),
            origin=str(data.get("origin", "reflection")),
            source_experience_ids=tuple(data.get("source_experience_ids", ())),
            source_session_ids=tuple(data.get("source_session_ids", ())),
            created_by=str(data.get("created_by", "learning_pipeline")),
            manual_override=bool(data.get("manual_override", False)),
            verified=bool(data.get("verified", True)),
            created_at_ms=int(data.get("created_at_ms", 0)),
        )


@dataclass(frozen=True, slots=True)
class StrategyAdoptionTrace:
    """Audit log of when, why, and how a strategy was considered, selected, or counterfactually bypassed."""

    trace_id: str
    session_id: str
    turn_id: str
    strategy_id: str
    retrieved: bool
    injected: bool
    considered: bool
    selected: bool
    execution_used: bool
    outcome_verified: bool
    counterfactual_baseline: str = ""
    timestamp_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LearningEffectResult:
    """Quantitative effect-size assessment (replaces false statistical significance)."""

    PROVEN: ClassVar[str] = "proven"
    NOT_PROVEN: ClassVar[str] = "not_proven"
    INCONCLUSIVE: ClassVar[str] = "inconclusive"

    learning_effect: str  # "proven", "not_proven", "inconclusive"
    absolute_improvement: float
    relative_improvement: float
    sample_count: int
    evidence_sufficient: bool
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def result(self) -> str:
        return self.learning_effect

    @property
    def arm_c_success(self) -> bool:
        return bool(
            self.details.get("control_c_accuracy", 0.0) > 0.0 or self.absolute_improvement > 0.0
        )

    @property
    def arm_a_success(self) -> bool:
        return bool(self.details.get("control_a_accuracy", 0.0) > 0.0)

    @property
    def effect_size(self) -> float:
        return (
            self.absolute_improvement
            if self.absolute_improvement > 0
            else max(0.0, self.relative_improvement)
        )


@dataclass(frozen=True, slots=True)
class EvidenceIndependence:
    """Tracks uniqueness across sessions, tasks, and targets to prevent pseudo-replication."""

    unique_sessions: int
    unique_tasks: int
    unique_targets: int
    total_observations: int
    independence_ratio: float = 1.0

    @property
    def is_independent(self) -> bool:
        if self.total_observations <= 1:
            return True
        # Must span across at least 2 distinct sessions, or 2 distinct tasks, or high independence ratio
        return self.unique_sessions >= 2 or self.unique_tasks >= 2 or self.independence_ratio >= 0.5

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_strategy_provenance(lineage: StrategyLineage) -> bool:
    """Validate that a strategy was autonomously learned from verified experiences without manual overrides."""
    if lineage.manual_override:
        return False
    if not lineage.verified:
        return False
    if lineage.origin != "reflection":
        return False
    if not lineage.source_experience_ids:
        return False
    return True
