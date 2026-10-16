"""jarvis_learning.datasets.dataset_revocation — revocation and invalidation tracking.

Tracks invalidation of datasets when downstream contamination, poisoning,
or evidence corruption is discovered.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetRevocationRecord:
    dataset_id: str
    reason: str
    revoked_by_operator_id: str
    timestamp: float
    affected_evidence_digests: tuple[str, ...] = ()
    affected_sample_ids: tuple[str, ...] = ()
    replacement_dataset_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "reason": self.reason,
            "revoked_by_operator_id": self.revoked_by_operator_id,
            "timestamp": self.timestamp,
            "affected_evidence_digests": list(self.affected_evidence_digests),
            "affected_sample_ids": list(self.affected_sample_ids),
            "replacement_dataset_id": self.replacement_dataset_id,
        }


class DatasetRevocationManager:
    """Maintains revoked dataset registry."""

    def __init__(self, db: Any = None) -> None:
        self._db = db
        self._revocations: dict[str, DatasetRevocationRecord] = {}

    def revoke_dataset(
        self,
        dataset_id: str,
        reason: str,
        operator_id: str,
        affected_evidence: list[str] | None = None,
        replacement_id: str = "",
    ) -> DatasetRevocationRecord:
        record = DatasetRevocationRecord(
            dataset_id=dataset_id,
            reason=reason,
            revoked_by_operator_id=operator_id,
            timestamp=time.time(),
            affected_evidence_digests=tuple(affected_evidence or []),
            replacement_dataset_id=replacement_id,
        )
        self._revocations[dataset_id] = record

        if self._db and hasattr(self._db, "store_dataset_revocation"):
            self._db.store_dataset_revocation(record.to_dict())

        return record

    def is_dataset_revoked(self, dataset_id: str) -> bool:
        return dataset_id in self._revocations


def is_dataset_revoked(db: Any, dataset_id: str) -> bool:
    """Check if a dataset is revoked in the manager or database."""
    if isinstance(db, DatasetRevocationManager):
        return db.is_dataset_revoked(dataset_id)
    if hasattr(db, "is_dataset_revoked"):
        return bool(db.is_dataset_revoked(dataset_id))
    return False
