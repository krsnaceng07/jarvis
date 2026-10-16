"""jarvis_learning.datasets.snapshot — frozen source experience snapshotting.

Guarantees dataset build consistency:
- Captures source high-water marks (cutoff_timestamp, cutoff_event_id).
- Computes deterministic source_snapshot_hash over candidate experiences.
- Ignores new incoming experiences recorded after the snapshot cutoff.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .canonicalization import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class ExperienceSourceSnapshot:
    """Immutable snapshot metadata capturing a fixed point in the experience store."""

    snapshot_id: str
    cutoff_timestamp: float
    cutoff_event_id: str
    source_snapshot_hash: str
    total_candidate_count: int
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "cutoff_timestamp": self.cutoff_timestamp,
            "cutoff_event_id": self.cutoff_event_id,
            "source_snapshot_hash": self.source_snapshot_hash,
            "total_candidate_count": self.total_candidate_count,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperienceSourceSnapshot:
        return cls(
            snapshot_id=str(data["snapshot_id"]),
            cutoff_timestamp=float(data["cutoff_timestamp"]),
            cutoff_event_id=str(data["cutoff_event_id"]),
            source_snapshot_hash=str(data["source_snapshot_hash"]),
            total_candidate_count=int(data["total_candidate_count"]),
            created_at=float(data["created_at"]),
        )


def compute_snapshot(
    experiences: list[Any],
    snapshot_timestamp: float | None = None,
) -> ExperienceSourceSnapshot:
    """Create a frozen snapshot metadata object from a candidate experience list."""
    if not experiences:
        return ExperienceSourceSnapshot(
            snapshot_id="snap_empty",
            cutoff_timestamp=0.0,
            cutoff_event_id="",
            source_snapshot_hash=hashlib.sha256(b"empty").hexdigest(),
            total_candidate_count=0,
            created_at=snapshot_timestamp or 0.0,
        )

    def _exp_ts(e: Any) -> float:
        return float(getattr(e, "created_at", getattr(e, "timestamp", 0.0)))

    # Sort experiences by (timestamp, id) for deterministic high-water mark
    sorted_exps = sorted(experiences, key=lambda e: (_exp_ts(e), getattr(e, "id", "")))
    latest = sorted_exps[-1]

    cutoff_ts = _exp_ts(latest)
    cutoff_id = getattr(latest, "id", "")

    # Hash the sequence of experience IDs and timestamps
    digest_input = [{"id": getattr(e, "id", ""), "ts": _exp_ts(e)} for e in sorted_exps]
    snap_hash = hashlib.sha256(canonical_json_bytes(digest_input)).hexdigest()
    snapshot_id = f"snap_{snap_hash[:16]}"

    return ExperienceSourceSnapshot(
        snapshot_id=snapshot_id,
        cutoff_timestamp=cutoff_ts,
        cutoff_event_id=cutoff_id,
        source_snapshot_hash=snap_hash,
        total_candidate_count=len(sorted_exps),
        created_at=snapshot_timestamp or cutoff_ts,
    )
