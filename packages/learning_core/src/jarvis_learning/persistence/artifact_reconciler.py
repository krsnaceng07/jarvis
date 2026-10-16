"""Artifact reconciler with forensic quarantine management (never silent delete).

Guarantees that uncommitted staging files or broken artifacts are preserved
in forensic quarantine, while committed artifacts are audited bit-for-bit against manifest digests.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import logging
from pathlib import Path
import shutil
from typing import Any

from jarvis_learning.persistence.artifact_manifest import PreRebootManifest
from jarvis_learning.persistence.models import QuarantineRecord

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class ReconciliationAudit:
    """Detailed audit report of post-reboot artifact reconciliation."""

    committed_verified: list[str]
    committed_corrupt: list[str]
    committed_missing: list[str]
    quarantine_records: list[QuarantineRecord]
    all_committed_intact: bool
    all_staging_quarantined: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "committed_verified": self.committed_verified,
            "committed_corrupt": self.committed_corrupt,
            "committed_missing": self.committed_missing,
            "quarantine_records": [q.to_dict() for q in self.quarantine_records],
            "all_committed_intact": self.all_committed_intact,
            "all_staging_quarantined": self.all_staging_quarantined,
        }


class ArtifactReconciler:
    """Audits storage directory against baseline manifest and manages forensic quarantine."""

    @classmethod
    def reconcile(
        cls,
        root_dir: Path,
        manifest: PreRebootManifest,
        transaction_id: str,
    ) -> ReconciliationAudit:
        """Execute post-reboot reconciliation, verifying committed files and quarantining staging."""
        quarantine_dir = root_dir / "_quarantine" / transaction_id
        quarantine_dir.mkdir(parents=True, exist_ok=True)

        staging_dir = root_dir / "_staging"
        quarantined: list[QuarantineRecord] = []

        # 1. Forensic quarantine of any remaining uncommitted staging files
        if staging_dir.exists():
            for p in staging_dir.glob("*"):
                if p.is_file():
                    digest = hashlib.sha256(p.read_bytes()).hexdigest()
                    dest = quarantine_dir / p.name
                    size = p.stat().st_size

                    # Atomic move into quarantine (NEVER DELETE)
                    shutil.move(str(p), str(dest))

                    record = QuarantineRecord(
                        original_path=str(p.relative_to(root_dir)).replace("\\", "/"),
                        quarantined_path=str(dest.relative_to(root_dir)).replace("\\", "/"),
                        file_size_bytes=size,
                        sha256_digest=digest,
                        reason="Uncommitted staging artifact abandoned across reboot boundary",
                        quarantined_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    )
                    quarantined.append(record)

        # Write forensic quarantine ledger
        if quarantined:
            ledger_file = quarantine_dir / "quarantine_ledger.json"
            ledger_file.write_text(
                json.dumps([q.to_dict() for q in quarantined], indent=2), encoding="utf-8"
            )

        # 2. Bit-for-bit SHA-256 validation of all committed artifacts
        verified: list[str] = []
        corrupt: list[str] = []
        missing: list[str] = []

        for entry in manifest.committed_files:
            file_path = root_dir / entry.relative_path
            if not file_path.exists():
                missing.append(entry.relative_path)
            else:
                actual_digest = hashlib.sha256(file_path.read_bytes()).hexdigest()
                if actual_digest == entry.sha256_digest:
                    verified.append(entry.relative_path)
                else:
                    corrupt.append(entry.relative_path)
                    # Quarantine corrupted committed file for forensic review
                    corrupt_dest = quarantine_dir / f"CORRUPT_{file_path.name}"
                    shutil.copy2(str(file_path), str(corrupt_dest))

        all_intact = len(corrupt) == 0 and len(missing) == 0
        staging_clean = not (staging_dir.exists() and any(staging_dir.glob("*")))

        return ReconciliationAudit(
            committed_verified=verified,
            committed_corrupt=corrupt,
            committed_missing=missing,
            quarantine_records=quarantined,
            all_committed_intact=all_intact,
            all_staging_quarantined=staging_clean,
        )


__all__ = ["ArtifactReconciler", "ReconciliationAudit"]
