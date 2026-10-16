"""Fine-grained Resource Arbitrator for Track 3.3.

HARD INVARIANTS:
1. Deadlock Prevention: Multiple resource claims are sorted alphabetically by
   composite_key before atomic multi-resource acquisition.
2. Fine-grained Browser Tabs: Locks per tab_id/domain origin, NOT coarse process locks.
3. Desktop Input: Strictly EXCLUSIVE; desktop focus/typing is single-task serialized.
4. Filesystem: EXCLUSIVE per target file path / directory, SHARED for read queries.
5. Fencing generation strictly increments with every acquisition.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import datetime
import uuid

from jarvis_agent.scheduling.models.resource import (
    ResourceClaim,
    ResourceLease,
)
from jarvis_agent.scheduling.storage.projection_store import ProjectionStore


@dataclass(frozen=True, slots=True)
class ArbitrationResult:
    """Result of attempting to acquire a set of resource claims."""

    granted: bool
    leases: list[ResourceLease] = field(default_factory=list)
    blocked_by_key: str | None = None
    reason: str | None = None


class ResourceArbitrator:
    """Arbitrates concurrent resource claims across tasks and workers."""

    def __init__(self, store: ProjectionStore) -> None:
        self._store = store

    def acquire_resources(
        self,
        claims: list[ResourceClaim],
        worker_id: str,
        lease_duration_seconds: float = 30.0,
    ) -> ArbitrationResult:
        """Atomically acquire multiple resource claims in deadlock-free sorted order."""
        if not claims:
            return ArbitrationResult(granted=True, leases=[])

        # Deadlock prevention: sort claims alphabetically by composite_key
        sorted_claims = sorted(claims, key=lambda c: c.composite_key)

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        expires_dt = now_dt + datetime.timedelta(seconds=lease_duration_seconds)
        now_str = now_dt.isoformat()
        expires_str = expires_dt.isoformat()

        granted_leases: list[ResourceLease] = []

        # Acquire sequentially; if any fails, roll back all previously acquired leases
        for claim in sorted_claims:
            lease_id = f"lease_{uuid.uuid4().hex[:12]}"
            lease = self._store.acquire_lease(
                claim=claim,
                lease_id=lease_id,
                worker_id=worker_id,
                acquired_at_utc=now_str,
                expires_at_utc=expires_str,
            )
            if lease is None:
                # Acquisition blocked; rollback granted leases in reverse order
                for acquired in reversed(granted_leases):
                    self._store.release_lease(
                        resource_key=acquired.claim.composite_key,
                        worker_id=worker_id,
                        generation=acquired.fencing_token.generation,
                    )
                return ArbitrationResult(
                    granted=False,
                    blocked_by_key=claim.composite_key,
                    reason=f"Resource {claim.composite_key} currently locked by active lease",
                )

            granted_leases.append(lease)

        return ArbitrationResult(granted=True, leases=granted_leases)

    def release_resources(self, leases: list[ResourceLease]) -> None:
        """Release granted leases."""
        for lease in leases:
            self._store.release_lease(
                resource_key=lease.claim.composite_key,
                worker_id=lease.worker_id,
                generation=lease.fencing_token.generation,
            )


__all__ = ["ArbitrationResult", "ResourceArbitrator"]
