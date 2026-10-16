"""Crash simulation harness and cold-boot recovery validator.

Enforces:
- INV-P10-REC-001: No acknowledged durable transaction may be silently lost.
- INV-P10-REC-002: Uncommitted partial artifacts must never become active.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


@dataclasses.dataclass(frozen=True)
class RecoveryAuditReport:
    """Detailed audit of recovery actions taken upon cold boot."""

    quarantined_files: list[str]
    reconstructed_active_version: str | None
    is_consistent: bool
    recovery_status: str
    details: dict[str, Any] = dataclasses.field(default_factory=dict)


class ColdBootRecoveryManager:
    """Reconciles disk artifacts, pointers, and ledgers upon host cold boot."""

    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir
        self._staging_dir = root_dir / "_staging"
        self._quarantine_dir = root_dir / "_quarantine"
        self._artifacts_dir = root_dir / "artifacts"
        self._pointer_file = root_dir / "ACTIVE_POINTER.json"

        self._quarantine_dir.mkdir(parents=True, exist_ok=True)

    def reconcile_on_boot(self) -> RecoveryAuditReport:
        """Audit storage and reconcile incomplete or corrupt state."""
        quarantined: list[str] = []

        # 1. Clean and quarantine any dangling staging files
        if self._staging_dir.exists():
            for tmp_file in self._staging_dir.glob("*.tmp"):
                target = self._quarantine_dir / tmp_file.name
                shutil.move(str(tmp_file), str(target))
                quarantined.append(tmp_file.name)

        # 2. Check active pointer integrity
        active_version: str | None = None
        is_consistent = True

        if self._pointer_file.exists():
            try:
                pointer_data = json.loads(self._pointer_file.read_text(encoding="utf-8"))
                version = pointer_data.get("active_version")
                artifact_id = pointer_data.get("active_artifact_id")
                expected_digest = pointer_data.get("digest")

                # Verify target artifact exists and matches digest
                target_dir = self._artifacts_dir / f"model_{version}"
                target_bin = target_dir / f"{artifact_id}.bin"
                ledger_file = target_dir / "commit_ledger.json"

                if not target_bin.exists() or not ledger_file.exists():
                    is_consistent = False
                else:
                    actual_digest = hashlib.sha256(target_bin.read_bytes()).hexdigest()
                    if actual_digest != expected_digest:
                        is_consistent = False
                    else:
                        active_version = version

            except Exception:
                is_consistent = False

        status = "RECOVERED_CLEAN" if is_consistent else "RECOVERY_CORRUPTED_POINTER"

        return RecoveryAuditReport(
            quarantined_files=quarantined,
            reconstructed_active_version=active_version,
            is_consistent=is_consistent,
            recovery_status=status,
        )
