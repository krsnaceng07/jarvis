"""Prioritized resource lease manager with active runtime protection.

Enforces INV-P10-HW-002: Resource governors must reserve guaranteed capacity
and headroom for the active JARVIS runtime.
"""

from __future__ import annotations

import dataclasses
import enum
import time


class LeasePriority(enum.IntEnum):
    """Priority tiers for hardware resource leases."""

    P0_VOICE_AUDIO = 0  # Highest priority, non-preemptible, guaranteed headroom
    P1_ACTIVE_TOOL = 1  # Active user tool execution
    P2_INTERACTIVE_UI = 2  # Desktop UI and dashboard queries
    P3_EVALUATION = 3  # Offline shadow model evaluation
    P4_TRAINING_SHADOW = 4  # Background dataset generation / shadow learning


@dataclasses.dataclass
class ResourceLease:
    """Individual granted resource allocation lease."""

    lease_id: str
    resource_type: str
    device_id: str
    owner: str
    priority: LeasePriority
    requested_amount: int
    granted_amount: int
    expiry_timestamp: float
    preemptible: bool
    is_active: bool = True

    def is_expired(self, current_time: float | None = None) -> bool:
        now = time.time() if current_time is None else current_time
        return now >= self.expiry_timestamp


class ResourceLeaseManager:
    """Manages resource leases with preemption of background tasks for P0/P1 workloads."""

    def __init__(self) -> None:
        self._leases: dict[str, ResourceLease] = {}
        self._counter = 0

    def acquire_lease(
        self,
        resource_type: str,
        device_id: str,
        owner: str,
        priority: LeasePriority,
        amount: int,
        total_capacity: int,
        ttl_sec: float = 60.0,
        current_time: float | None = None,
    ) -> ResourceLease | None:
        """Attempt to acquire a resource lease with preemption if necessary."""
        now = time.time() if current_time is None else current_time
        self.clean_expired(now)

        # Calculate currently allocated amount on this device
        allocated = sum(
            lease.granted_amount
            for lease in self._leases.values()
            if lease.is_active
            and lease.resource_type == resource_type
            and lease.device_id == device_id
        )

        available = total_capacity - allocated

        if available >= amount:
            # Grant immediately
            self._counter += 1
            lease_id = f"lease_{self._counter:05d}"
            preemptible = priority >= LeasePriority.P3_EVALUATION
            lease = ResourceLease(
                lease_id=lease_id,
                resource_type=resource_type,
                device_id=device_id,
                owner=owner,
                priority=priority,
                requested_amount=amount,
                granted_amount=amount,
                expiry_timestamp=now + ttl_sec,
                preemptible=preemptible,
                is_active=True,
            )
            self._leases[lease_id] = lease
            return lease

        # If high priority (P0 or P1), attempt to preempt lower-priority preemptible leases
        if priority <= LeasePriority.P1_ACTIVE_TOOL:
            preemptible_leases = [
                lease_item
                for lease_item in self._leases.values()
                if lease_item.is_active
                and lease_item.resource_type == resource_type
                and lease_item.device_id == device_id
                and lease_item.preemptible
                and lease_item.priority > priority
            ]
            # Sort by lowest priority first (P4 down to P3)
            preemptible_leases.sort(key=lambda x: x.priority, reverse=True)

            reclaimed = 0
            for victim in preemptible_leases:
                victim.is_active = False
                reclaimed += victim.granted_amount
                if available + reclaimed >= amount:
                    break

            if available + reclaimed >= amount:
                self._counter += 1
                lease_id = f"lease_{self._counter:05d}"
                lease = ResourceLease(
                    lease_id=lease_id,
                    resource_type=resource_type,
                    device_id=device_id,
                    owner=owner,
                    priority=priority,
                    requested_amount=amount,
                    granted_amount=amount,
                    expiry_timestamp=now + ttl_sec,
                    preemptible=False,
                    is_active=True,
                )
                self._leases[lease_id] = lease
                return lease

        # Insufficient resources and cannot preempt
        return None

    def release_lease(self, lease_id: str) -> bool:
        """Explicitly release an active lease."""
        if lease_id in self._leases:
            self._leases[lease_id].is_active = False
            return True
        return False

    def clean_expired(self, current_time: float | None = None) -> int:
        """Deactivate all expired leases."""
        now = time.time() if current_time is None else current_time
        cleaned = 0
        for lease in self._leases.values():
            if lease.is_active and lease.is_expired(now):
                lease.is_active = False
                cleaned += 1
        return cleaned

    def get_active_leases(self) -> list[ResourceLease]:
        return [lease_item for lease_item in self._leases.values() if lease_item.is_active]
