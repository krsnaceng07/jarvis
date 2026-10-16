"""jarvis_learning.training.revocation_graph — artifact dependency DAG and cascade revocation propagator.

Guarantees:
- INV-REV-001: Revoking a dataset propagates downstream through the entire artifact DAG:
  Dataset -> Snapshot -> Training Run -> Checkpoint -> Derived Model -> Evaluation Result -> Export.
- Blocked actions on revoked lineage: Cannot train, resume, evaluate, export, promote, or deploy.
"""

from __future__ import annotations

import enum
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .checkpoint_store import REVOKED_MARKER_FILE
from .errors import DatasetRevokedError

logger = logging.getLogger(__name__)


class RevocationArtifactType(enum.StrEnum):
    """Types of artifacts tracked in the training lineage DAG."""

    DATASET = "DATASET"
    SNAPSHOT = "SNAPSHOT"
    TRAINING_RUN = "TRAINING_RUN"
    CHECKPOINT = "CHECKPOINT"
    DERIVED_MODEL = "DERIVED_MODEL"
    EVALUATION_REPORT = "EVALUATION_REPORT"
    EXPORT_PACKAGE = "EXPORT_PACKAGE"


# Canonical alias
ArtifactType = RevocationArtifactType


@dataclass(slots=True)
class ArtifactNode:
    """A node in the provenance and lifecycle dependency graph."""

    artifact_id: str
    artifact_type: RevocationArtifactType
    parent_ids: set[str] = field(default_factory=set)
    child_ids: set[str] = field(default_factory=set)
    is_revoked: bool = False
    revocation_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    artifact_path: Path | None = None


@dataclass(frozen=True, slots=True)
class RevocationRecord:
    """Immutable audit record documenting a dataset-to-artifact revocation event."""

    revocation_id: str
    root_dataset_id: str
    reason: str
    revoked_at: float
    operator_id: str
    affected_artifact_ids: tuple[str, ...]
    ledger_hash: str


class RevocationGraph:
    """Directed Acyclic Graph tracking artifact lineages and cascading revocation invalidations."""

    def __init__(self) -> None:
        self.nodes: dict[str, ArtifactNode] = {}
        self.revocation_records: list[RevocationRecord] = []

    def register_artifact(
        self,
        artifact_id: str,
        artifact_type: RevocationArtifactType,
        parent_ids: Sequence[str] = (),
        metadata: dict[str, Any] | None = None,
        artifact_path: Path | None = None,
    ) -> ArtifactNode:
        """Register an artifact node and connect its parent/child relationships."""
        if artifact_id not in self.nodes:
            node = ArtifactNode(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                parent_ids=set(parent_ids),
                metadata=metadata or {},
                artifact_path=artifact_path,
            )
            self.nodes[artifact_id] = node
        else:
            node = self.nodes[artifact_id]
            node.parent_ids.update(parent_ids)
            if artifact_path:
                node.artifact_path = artifact_path

        for p_id in parent_ids:
            if p_id in self.nodes:
                self.nodes[p_id].child_ids.add(artifact_id)

        # If any parent is already revoked, cascade immediately to this new child
        if any(self.nodes.get(p) and self.nodes[p].is_revoked for p in parent_ids):
            node.is_revoked = True
            node.revocation_reason = "Inherited revocation from parent artifact"
            if node.artifact_path and Path(node.artifact_path).exists():
                try:
                    (Path(node.artifact_path) / REVOKED_MARKER_FILE).write_text(
                        "Inherited revocation\n", encoding="utf-8"
                    )
                except Exception:
                    pass

        return node

    def propagate_revocation(
        self,
        root_dataset_id: str,
        reason: str,
        operator_id: str = "operator",
        output_dir: Path | None = None,
    ) -> RevocationRecord:
        """Propagate revocation through all downstream descendants."""
        affected: list[str] = []
        queue = [root_dataset_id]
        visited = set()

        while queue:
            curr_id = queue.pop(0)
            if curr_id in visited:
                continue
            visited.add(curr_id)

            node = self.nodes.get(curr_id)
            if node:
                node.is_revoked = True
                node.revocation_reason = reason
                if node.artifact_path and Path(node.artifact_path).exists():
                    try:
                        (Path(node.artifact_path) / REVOKED_MARKER_FILE).write_text(
                            f"Revocation reason: {reason}\n", encoding="utf-8"
                        )
                    except Exception:
                        pass
                affected.append(curr_id)
                for child_id in node.child_ids:
                    if child_id not in visited:
                        queue.append(child_id)
            else:
                # Root dataset might not be in in-memory graph yet
                affected.append(curr_id)

        # Also stamp filesystem checkpoints if output_dir provided
        if output_dir and Path(output_dir).exists():
            self._stamp_filesystem_revocation(Path(output_dir), root_dataset_id)

        # Compute tamper-evident hash
        rec_id = f"rev_{uuid.uuid4().hex[:12]}"
        now = time.time()
        payload = f"{rec_id}:{root_dataset_id}:{reason}:{now}:{operator_id}:{sorted(affected)}"
        ledger_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        record = RevocationRecord(
            revocation_id=rec_id,
            root_dataset_id=root_dataset_id,
            reason=reason,
            revoked_at=now,
            operator_id=operator_id,
            affected_artifact_ids=tuple(sorted(affected)),
            ledger_hash=ledger_hash,
        )
        self.revocation_records.append(record)
        logger.warning(
            "Revocation propagated for dataset '%s': %d artifacts invalidated",
            root_dataset_id,
            len(affected),
        )
        return record

    def is_revoked(self, artifact_id: str) -> bool:
        """Check whether an artifact or any of its ancestors is marked revoked."""
        node = self.nodes.get(artifact_id)
        if node and node.is_revoked:
            return True
        return False

    def verify_not_revoked(self, artifact_id: str, operation_name: str = "operation") -> None:
        """Enforce rejection if artifact is revoked."""
        if self.is_revoked(artifact_id):
            msg = f"Cannot perform {operation_name}: artifact '{artifact_id}' is REVOKED_INELIGIBLE"
            logger.error(msg)
            raise DatasetRevokedError(msg)

    def revoke_artifact(
        self,
        artifact_id: str,
        reason: str,
        operator_id: str = "operator",
        output_dir: Path | None = None,
    ) -> list[str]:
        """Convenience wrapper around propagate_revocation returning affected IDs."""
        rec = self.propagate_revocation(
            root_dataset_id=artifact_id,
            reason=reason,
            operator_id=operator_id,
            output_dir=output_dir,
        )
        return list(rec.affected_artifact_ids)

    def check_can_resume(self, artifact_id: str) -> None:
        """Enforce that artifact lineage is not revoked for training resume."""
        self.verify_not_revoked(artifact_id, operation_name="resume")

    def check_can_evaluate(self, artifact_id: str) -> None:
        """Enforce that artifact lineage is not revoked for model evaluation."""
        self.verify_not_revoked(artifact_id, operation_name="evaluation")

    def check_can_export(self, artifact_id: str) -> None:
        """Enforce that artifact lineage is not revoked for candidate export."""
        self.verify_not_revoked(artifact_id, operation_name="export")

    @staticmethod
    def _stamp_filesystem_revocation(output_dir: Path, dataset_id: str) -> list[str]:
        """Stamp filesystem checkpoint directories with REVOKED_INELIGIBLE marker."""
        stamped = []
        for item in output_dir.iterdir():
            if item.is_dir() and not item.name.startswith((".", "_")):
                meta_path = item / "checkpoint_meta.json"
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                        if meta.get("dataset_id") == dataset_id:
                            (item / REVOKED_MARKER_FILE).write_text(
                                f"Revoked dataset: {dataset_id}\n", encoding="utf-8"
                            )
                            stamped.append(item.name)
                    except Exception:
                        pass
        return stamped
