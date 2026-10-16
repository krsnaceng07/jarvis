"""jarvis_learning.datasets.schema — common dataset contract.

Every formatter outputs ``DatasetSample`` through this shared schema.
No formatter invents its own format.  The schema includes label
quality, sample weight, provenance, and lineage fields that travel
with every sample through the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class DatasetTarget(StrEnum):
    """Which model a dataset is built for."""

    TOOL_POLICY = "tool_policy"
    MEMORY_RERANKER = "memory_reranker"
    STRATEGY_PREDICTOR = "strategy_predictor"


class LabelQuality(StrEnum):
    """How good a training label is."""

    OPTIMAL = "optimal"  # best verified behavior
    ACCEPTABLE = "acceptable"  # worked, not ideal
    SUBOPTIMAL = "suboptimal"  # worked with unnecessary steps
    WRONG = "wrong"  # incorrect tool/action
    UNSAFE = "unsafe"  # security/permission violation
    UNKNOWN = "unknown"  # cannot determine


class FailureType(StrEnum):
    """Why a tool call failed — determines label quality."""

    TOOL_SELECTION_ERROR = "tool_selection_error"
    TOOL_ARGUMENT_ERROR = "tool_argument_error"
    ENVIRONMENT_ERROR = "environment_error"
    EXTERNAL_SERVICE_ERROR = "external_service_error"
    USER_INPUT_ERROR = "user_input_error"
    RECOVERY_ERROR = "recovery_error"
    FALSE_COMPLETION = "false_completion"


# ── Default sample weights by label quality ──────────────────

DEFAULT_SAMPLE_WEIGHTS: dict[str, float] = {
    LabelQuality.OPTIMAL: 1.0,
    LabelQuality.ACCEPTABLE: 0.5,
    LabelQuality.SUBOPTIMAL: 0.0,
    LabelQuality.WRONG: 1.0,  # negative learning
    LabelQuality.UNSAFE: 1.0,  # safety rejection learning
    LabelQuality.UNKNOWN: 0.0,
}


@dataclass(frozen=True, slots=True)
class DatasetSample:
    """One training sample — the universal format through the pipeline.

    Every formatter, deduplicator, splitter, and validator operates
    on this type.  Target-specific fields live in ``input_data`` and
    ``label``.
    """

    sample_id: str
    target: str  # DatasetTarget value
    input_data: dict[str, Any]  # model input
    label: dict[str, Any]  # training label
    label_quality: str  # LabelQuality value
    label_confidence: float  # 0.0–1.0
    label_source: str  # how the label was determined
    sample_weight: float  # training weight
    provenance: dict[str, Any]  # TrainingSampleProvenance dict
    lineage: dict[str, Any]  # SampleLineage dict
    quality_score: float
    split: str = ""  # "train" / "validation" / "test" / "ood_test" / "golden_holdout" / "challenge"
    source_experience_id: str = ""
    schema_version: str = "1"
    # Phase 6 additions:
    logical_sample_id: str = ""
    materialized_sample_id: str = ""
    evidence_digest: str = ""
    sample_usage: str = "sft"
    outcome_vector: dict[str, Any] = field(default_factory=dict)
    causal_attribution: dict[str, Any] = field(default_factory=dict)
    strategy_lineage: dict[str, Any] = field(default_factory=dict)
    redaction_records: list[dict[str, Any]] = field(default_factory=list)

    def to_jsonl_dict(self) -> dict[str, Any]:
        """Serialize for JSONL output."""
        return {
            "sample_id": self.sample_id,
            "target": self.target,
            "input_data": self.input_data,
            "label": self.label,
            "label_quality": self.label_quality,
            "label_confidence": self.label_confidence,
            "label_source": self.label_source,
            "sample_weight": self.sample_weight,
            "provenance": self.provenance,
            "lineage": self.lineage,
            "quality_score": self.quality_score,
            "split": self.split,
            "source_experience_id": self.source_experience_id,
            "schema_version": self.schema_version,
            "logical_sample_id": self.logical_sample_id or self.sample_id,
            "materialized_sample_id": self.materialized_sample_id or self.sample_id,
            "evidence_digest": self.evidence_digest,
            "sample_usage": self.sample_usage,
            "outcome_vector": self.outcome_vector,
            "causal_attribution": self.causal_attribution,
            "strategy_lineage": self.strategy_lineage,
            "redaction_records": self.redaction_records,
        }

    @classmethod
    def from_jsonl_dict(cls, data: dict[str, Any]) -> DatasetSample:
        """Deserialize from JSONL."""
        s_id = data["sample_id"]
        return cls(
            sample_id=s_id,
            target=data["target"],
            input_data=data["input_data"],
            label=data["label"],
            label_quality=data["label_quality"],
            label_confidence=data.get("label_confidence", 0.0),
            label_source=data.get("label_source", "unknown"),
            sample_weight=data.get("sample_weight", 1.0),
            provenance=data.get("provenance", {}),
            lineage=data.get("lineage", {}),
            quality_score=data.get("quality_score", 0.0),
            split=data.get("split", ""),
            source_experience_id=data.get("source_experience_id", ""),
            schema_version=data.get("schema_version", "2"),
            logical_sample_id=data.get("logical_sample_id", s_id),
            materialized_sample_id=data.get("materialized_sample_id", s_id),
            evidence_digest=data.get("evidence_digest", ""),
            sample_usage=data.get("sample_usage", "sft"),
            outcome_vector=data.get("outcome_vector", {}),
            causal_attribution=data.get("causal_attribution", {}),
            strategy_lineage=data.get("strategy_lineage", {}),
            redaction_records=data.get("redaction_records", []),
        )

    def with_split(self, split: str) -> DatasetSample:
        """Return a copy assigned to a split."""
        d = self.to_jsonl_dict()
        d["split"] = split
        return DatasetSample.from_jsonl_dict(d)

    @staticmethod
    def default_weight_for(label_quality: str) -> float:
        """Look up default sample weight for a label quality."""
        return DEFAULT_SAMPLE_WEIGHTS.get(label_quality, 0.0)
