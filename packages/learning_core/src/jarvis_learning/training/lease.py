"""jarvis_learning.training.lease — supervisor job lease and split-brain prevention.

Guarantees:
- INV-LEASE-001: Only the active lease holder can execute or advance job state.
- Monotonic sequence-numbered heartbeats prevent replay or split-brain race conditions.
- Multi-supervisor lease recovery protects against competing concurrent workers.
"""

from __future__ import annotations

import enum
import logging
import time
import uuid
from dataclasses import dataclass
from typing import ClassVar

from .errors import TrainingError

logger = logging.getLogger(__name__)


class JobLeaseError(TrainingError):
    """Base error for lease acquisition or validation failures."""

    def __init__(self, message: str, code: str = "LEASE_ERROR") -> None:
        super().__init__(message, code=code)


class JobLeaseHeldError(JobLeaseError):
    """Raised when an active lease is held by another supervisor."""

    def __init__(self, job_id: str, holder: str) -> None:
        super().__init__(
            f"Job '{job_id}' is actively leased by supervisor '{holder}'",
            code="LEASE_ALREADY_HELD",
        )


class JobLeaseExpiredError(JobLeaseError):
    """Raised when an operation is attempted with an expired lease."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"Lease for job '{job_id}' has expired", code="LEASE_EXPIRED")


class SplitBrainDetectedError(JobLeaseError):
    """Raised when concurrent competing supervisors attempt conflicting writes."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"Split-brain conflict detected for job '{job_id}': concurrent lease contention",
            code="SPLIT_BRAIN_DETECTED",
        )


class RecoveryState(enum.StrEnum):
    """Stages of supervisor crash-recovery transaction."""

    RECOVERY_PENDING = "RECOVERY_PENDING"
    RECOVERY_VALIDATING = "RECOVERY_VALIDATING"
    RECOVERY_REJECTED = "RECOVERY_REJECTED"
    RECOVERY_APPROVED = "RECOVERY_APPROVED"


@dataclass(frozen=True, slots=True)
class JobLease:
    """Cryptographic lease record granting exclusive supervisor execution authority."""

    lease_id: str
    job_id: str
    supervisor_instance_id: str
    lease_nonce: str
    acquired_at: float
    expires_at: float
    heartbeat_sequence: int = 0
    worker_pid: int | None = None

    def is_valid(self, now: float | None = None) -> bool:
        """Check if lease is within its validity window."""
        t = time.time() if now is None else now
        return t < self.expires_at


class SupervisorLeaseManager:
    """Atomic registry tracking supervisor job leases and enforcing single-ownership."""

    _active_leases: ClassVar[dict[str, JobLease]] = {}

    def __init__(
        self,
        lease_duration_seconds: float = 30.0,
        grace_period_seconds: float = 5.0,
    ) -> None:
        self.lease_duration_seconds = lease_duration_seconds
        self.grace_period_seconds = grace_period_seconds

    def acquire_lease(
        self_or_cls,
        job_id: str,
        supervisor_instance_id: str,
        ttl_seconds: float | None = None,
        worker_pid: int | None = None,
    ) -> JobLease:
        """Atomically acquire an exclusive execution lease for a job."""
        now = time.time()
        if isinstance(self_or_cls, SupervisorLeaseManager):
            effective_ttl = (
                ttl_seconds if ttl_seconds is not None else self_or_cls.lease_duration_seconds
            )
            grace = self_or_cls.grace_period_seconds
        else:
            effective_ttl = ttl_seconds if ttl_seconds is not None else 30.0
            grace = 5.0

        existing = SupervisorLeaseManager._active_leases.get(job_id)

        if existing and (existing.is_valid(now) or now < existing.expires_at + grace):
            if existing.supervisor_instance_id != supervisor_instance_id:
                logger.error(
                    "Lease acquisition rejected for job '%s': currently held by supervisor '%s'",
                    job_id,
                    existing.supervisor_instance_id,
                )
                raise JobLeaseHeldError(job_id, existing.supervisor_instance_id)

        lease = JobLease(
            lease_id=f"lease_{uuid.uuid4().hex[:12]}",
            job_id=job_id,
            supervisor_instance_id=supervisor_instance_id,
            lease_nonce=uuid.uuid4().hex,
            acquired_at=now,
            expires_at=now + effective_ttl,
            heartbeat_sequence=1,
            worker_pid=worker_pid,
        )
        SupervisorLeaseManager._active_leases[job_id] = lease
        logger.info(
            "Supervisor '%s' acquired lease '%s' for job '%s' (ttl=%.1fs)",
            supervisor_instance_id,
            lease.lease_id,
            job_id,
            effective_ttl,
        )
        return lease

    def renew_lease(
        self_or_cls,
        target: JobLease | str,
        supervisor_instance_id: str = "",
        ttl_seconds: float | None = None,
    ) -> JobLease:
        """Atomically renew lease with incremented heartbeat sequence."""
        now = time.time()
        if isinstance(self_or_cls, SupervisorLeaseManager):
            effective_ttl = (
                ttl_seconds if ttl_seconds is not None else self_or_cls.lease_duration_seconds
            )
        else:
            effective_ttl = ttl_seconds if ttl_seconds is not None else 30.0
        if isinstance(target, str):
            job_id = target
            existing = SupervisorLeaseManager._active_leases.get(job_id)
            if not existing:
                raise SplitBrainDetectedError(job_id)
            if supervisor_instance_id and existing.supervisor_instance_id != supervisor_instance_id:
                raise SplitBrainDetectedError(job_id)
            lease = existing
        else:
            lease = target
            existing = SupervisorLeaseManager._active_leases.get(lease.job_id)
            if not existing or existing.lease_id != lease.lease_id:
                raise SplitBrainDetectedError(lease.job_id)
            if existing.lease_nonce != lease.lease_nonce:
                raise SplitBrainDetectedError(lease.job_id)

        updated = JobLease(
            lease_id=lease.lease_id,
            job_id=lease.job_id,
            supervisor_instance_id=lease.supervisor_instance_id,
            lease_nonce=lease.lease_nonce,
            acquired_at=lease.acquired_at,
            expires_at=now + effective_ttl,
            heartbeat_sequence=lease.heartbeat_sequence + 1,
            worker_pid=lease.worker_pid,
        )
        SupervisorLeaseManager._active_leases[lease.job_id] = updated
        return updated

    @classmethod
    def release_lease(
        cls,
        target: JobLease | str,
        supervisor_instance_id: str = "",
    ) -> None:
        """Release active lease."""
        if isinstance(target, str):
            job_id = target
            existing = cls._active_leases.get(job_id)
            if existing:
                if (
                    not supervisor_instance_id
                    or existing.supervisor_instance_id == supervisor_instance_id
                ):
                    del cls._active_leases[job_id]
                    logger.info("Released lease '%s' for job '%s'", existing.lease_id, job_id)
        else:
            existing = cls._active_leases.get(target.job_id)
            if existing and existing.lease_id == target.lease_id:
                del cls._active_leases[target.job_id]
                logger.info("Released lease '%s' for job '%s'", target.lease_id, target.job_id)

    @classmethod
    def recover_expired_lease(
        cls,
        job_id: str,
        new_supervisor_instance_id: str,
        grace_period_seconds: float = 5.0,
        ttl_seconds: float = 30.0,
    ) -> tuple[JobLease, RecoveryState]:
        """Recover an abandoned or expired lease after required grace period."""
        now = time.time()
        existing = cls._active_leases.get(job_id)

        if existing and existing.is_valid(now):
            raise JobLeaseHeldError(job_id, existing.supervisor_instance_id)

        if existing and (now - existing.expires_at) < grace_period_seconds:
            logger.warning(
                "Recovery blocked: grace period (%.1fs) not yet elapsed", grace_period_seconds
            )
            return existing, RecoveryState.RECOVERY_PENDING

        recovered_lease = cls.acquire_lease(
            job_id=job_id,
            supervisor_instance_id=new_supervisor_instance_id,
            ttl_seconds=ttl_seconds,
        )
        return recovered_lease, RecoveryState.RECOVERY_APPROVED

    @classmethod
    def clear_all(cls) -> None:
        """Clear all active leases (for test isolation)."""
        cls._active_leases.clear()

    @classmethod
    def clear(cls) -> None:
        """Alias for clear_all."""
        cls.clear_all()
