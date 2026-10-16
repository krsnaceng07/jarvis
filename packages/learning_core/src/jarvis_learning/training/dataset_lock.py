"""jarvis_learning.training.dataset_lock — dataset input locking and single-job concurrency.

Pins dataset snapshot immutability during execution, monitors for revocation events
mid-training, and enforces a global single-job concurrency boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from ..datasets.dataset_revocation import is_dataset_revoked
from .errors import ConcurrencyLimitError, DatasetLockError, DatasetRevokedError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TrainingInputLock:
    """Manages an active lock on a dataset snapshot during training."""

    dataset_id: str
    manifest_hash: str
    dataset_dir: Path
    db_path: Path | None = None
    is_active: bool = False

    def acquire(self) -> None:
        """Acquire the input lock and verify initial revocation status."""
        if self.db_path and self.db_path.exists():
            if is_dataset_revoked(self.db_path, self.dataset_id):
                raise DatasetRevokedError(
                    f"Dataset '{self.dataset_id}' is revoked; cannot acquire lock"
                )
        self.is_active = True
        logger.info("Training input lock acquired for dataset='%s'", self.dataset_id)

    def verify_still_valid(self) -> bool:
        """Verify that the locked dataset has not been revoked or tampered with."""
        if not self.is_active:
            raise DatasetLockError("Input lock is not active")

        if self.db_path and self.db_path.exists():
            if is_dataset_revoked(self.db_path, self.dataset_id):
                self.is_active = False
                logger.error(
                    "Dataset '%s' was revoked during active training execution",
                    self.dataset_id,
                )
                raise DatasetRevokedError(
                    f"Dataset '{self.dataset_id}' was REVOKED_DURING_EXECUTION"
                )
        return True

    def release(self) -> None:
        """Release the input lock."""
        self.is_active = False
        logger.info("Training input lock released for dataset='%s'", self.dataset_id)


class ConcurrencyController:
    """Enforces max_concurrent_training_jobs = 1 across the workspace."""

    _active_job_id: str | None = None

    @classmethod
    def try_acquire_slot(cls, job_id: str) -> bool:
        """Attempt to acquire the single execution slot."""
        if cls._active_job_id is not None and cls._active_job_id != job_id:
            logger.warning(
                "Training concurrency limit reached (active_job='%s', requested_job='%s')",
                cls._active_job_id,
                job_id,
            )
            return False
        cls._active_job_id = job_id
        return True

    @classmethod
    def acquire_slot(cls, job_id: str) -> None:
        """Acquire slot or raise ConcurrencyLimitError."""
        if not cls.try_acquire_slot(job_id):
            raise ConcurrencyLimitError(
                f"Concurrent training jobs are not permitted (limit=1): cannot start training job '{job_id}' "
                f"while active job '{cls._active_job_id}' is running"
            )

    @classmethod
    def release_slot(cls, job_id: str) -> None:
        """Release the slot if held by this job."""
        if cls._active_job_id == job_id:
            cls._active_job_id = None
            logger.info("Released training execution slot for job='%s'", job_id)

    @classmethod
    def get_active_job(cls) -> str | None:
        """Return ID of currently running job, if any."""
        return cls._active_job_id
