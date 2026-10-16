"""Independent persistence reference oracle.

Maintains an isolated ground-truth model of expected committed artifacts, active generations,
and database row counts captured before reboot, avoiding circular self-referential validation.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class ExpectedStateSnapshot:
    """Expected state attributes captured independently before reboot."""

    transaction_id: str
    expected_generation: int
    expected_active_artifact_id: str
    expected_committed_count: int
    expected_db_rows: int
    expected_staging_quarantined_count: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class PersistenceReferenceModel:
    """Independent oracle auditing post-reboot observations against pre-reboot expectations."""

    @classmethod
    def evaluate(
        cls,
        expected: ExpectedStateSnapshot,
        observed_generation: int | None,
        observed_active_artifact_id: str | None,
        observed_committed_verified_count: int,
        observed_db_rows: int,
        observed_quarantined_count: int,
    ) -> tuple[bool, list[str]]:
        """Compare observed post-reboot recovery state against independent reference oracle."""
        discrepancies: list[str] = []

        if observed_generation != expected.expected_generation:
            discrepancies.append(
                f"Generation mismatch: expected {expected.expected_generation}, observed {observed_generation}"
            )

        if observed_active_artifact_id != expected.expected_active_artifact_id:
            discrepancies.append(
                f"Active artifact mismatch: expected {expected.expected_active_artifact_id}, observed {observed_active_artifact_id}"
            )

        if observed_committed_verified_count != expected.expected_committed_count:
            discrepancies.append(
                f"Committed artifact count mismatch: expected {expected.expected_committed_count}, verified {observed_committed_verified_count}"
            )

        if observed_db_rows != expected.expected_db_rows:
            discrepancies.append(
                f"Database rows mismatch: expected {expected.expected_db_rows}, observed {observed_db_rows}"
            )

        if observed_quarantined_count != expected.expected_staging_quarantined_count:
            discrepancies.append(
                f"Quarantine count mismatch: expected {expected.expected_staging_quarantined_count}, observed {observed_quarantined_count}"
            )

        matches_oracle = len(discrepancies) == 0
        return matches_oracle, discrepancies


__all__ = ["ExpectedStateSnapshot", "PersistenceReferenceModel"]
