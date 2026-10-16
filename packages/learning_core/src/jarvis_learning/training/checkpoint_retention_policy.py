"""jarvis_learning.training.checkpoint_retention_policy — checkpoint lifecycle retention and cleanup.

Retains best checkpoint, latest checkpoint, pre-failure snapshot, and operator-pinned
checkpoints, pruning intermediate draft snapshots to respect storage limits.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .checkpoint_store import CheckpointMetadata, CheckpointStore

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CheckpointRetentionPolicy:
    """Rules for retaining checkpoints and pruning intermediate drafts."""

    max_retained_checkpoints: int = 5
    best_checkpoint_id: str | None = None
    latest_checkpoint_id: str | None = None
    pre_failure_checkpoint_id: str | None = None
    pinned_checkpoint_ids: set[str] = field(default_factory=set)

    def pin_checkpoint(self, checkpoint_id: str) -> None:
        """Mark a checkpoint as operator-pinned to prevent pruning."""
        self.pinned_checkpoint_ids.add(checkpoint_id)

    def update_best(self, checkpoint_id: str) -> None:
        """Update best checkpoint identity."""
        self.best_checkpoint_id = checkpoint_id

    def update_latest(self, checkpoint_id: str) -> None:
        """Update latest checkpoint identity."""
        self.latest_checkpoint_id = checkpoint_id

    def mark_pre_failure(self, checkpoint_id: str) -> None:
        """Preserve checkpoint recorded immediately before a failure or abort."""
        self.pre_failure_checkpoint_id = checkpoint_id

    def prune_checkpoints(self, checkpoints_dir: Path) -> list[str]:
        """Prune unneeded checkpoints in directory, returning pruned checkpoint names."""
        if not checkpoints_dir.exists():
            return []

        dirs = [
            d for d in checkpoints_dir.iterdir() if d.is_dir() and not d.name.startswith(("_", "."))
        ]
        if len(dirs) <= self.max_retained_checkpoints:
            return []

        # Read metadata for each
        meta_list: list[CheckpointMetadata] = []
        for d in dirs:
            try:
                meta = CheckpointStore.verify_checkpoint(d)
                meta_list.append(meta)
            except Exception:
                # Corrupt or incomplete, eligible for cleanup
                pass

        # Sort by step ascending
        meta_list.sort(key=lambda m: m.step)

        protected_ids = {
            self.best_checkpoint_id,
            self.latest_checkpoint_id,
            self.pre_failure_checkpoint_id,
            *self.pinned_checkpoint_ids,
        }

        pruned: list[str] = []
        for meta in meta_list:
            if len(meta_list) - len(pruned) <= self.max_retained_checkpoints:
                break
            if meta.checkpoint_id not in protected_ids:
                try:
                    shutil.rmtree(meta.path)
                    pruned.append(meta.checkpoint_id)
                    logger.info("Pruned intermediate checkpoint '%s'", meta.checkpoint_id)
                except Exception as exc:
                    logger.warning("Failed to prune checkpoint '%s': %s", meta.path, exc)

        return pruned
