"""5-Level Evidence Ladder and Ambiguity Reconciliation models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
from typing import Any


class EvidenceLevel(IntEnum):
    """Strict 5-level hierarchy required to declare a node VERIFIED."""

    LEVEL_0_NO_EVIDENCE = 0  # Unstarted or missing records
    LEVEL_1_SCHEDULER_PROJECTION = 1  # Local scheduler projection record exists
    LEVEL_2_EXECUTION_LEDGER = 2  # Track 3.2 IdempotencyLedger COMPLETED state
    LEVEL_3_MACHINE_OBSERVATION = 3  # Cryptographic machine observations verified
    LEVEL_4_INDEPENDENT_VERIFIED = 4  # StateVerifier passed postcondition checks
    LEVEL_5_DURABLE_EVENT_COMMIT = 5  # Durably committed NODE_VERIFIED event in EventStore


@dataclass(frozen=True, slots=True)
class AmbiguityRecord:
    """Audit record capturing an in-flight unverified execution needing reconciliation."""

    node_id: str
    task_id: str
    execution_id: str
    idempotency_key: str
    capability_target: str
    side_effect_class: str
    evidence_level_reached: EvidenceLevel
    unverified_reason: str
    reconciliation_attempt: int = 1
    reconciliation_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["evidence_level_reached"] = self.evidence_level_reached.value
        return d


__all__ = ["AmbiguityRecord", "EvidenceLevel"]
