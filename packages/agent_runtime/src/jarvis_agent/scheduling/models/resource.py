"""Fine-grained resource model, claims, leases, and fencing tokens."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import datetime
from enum import Enum
from typing import Any


class ResourceClass(str, Enum):
    """Closed classification of physical and logical system resources."""

    DESKTOP_INPUT = "DESKTOP_INPUT"  # Exclusive: keyboard / mouse interaction
    DESKTOP_WINDOW = "DESKTOP_WINDOW"  # Target-specific: window_id / handle
    BROWSER_TAB = "BROWSER_TAB"  # Target-specific: tab_id / domain origin
    BROWSER_INSTANCE = "BROWSER_INSTANCE"  # Process instance
    FILESYSTEM_PATH = "FILESYSTEM_PATH"  # Exclusive: write locks per path/directory
    FILESYSTEM_READ = "FILESYSTEM_READ"  # Shared concurrent read access
    PROCESS_SLOT = "PROCESS_SLOT"  # Shared process slot pool
    NETWORK_ROUTE = "NETWORK_ROUTE"  # Route-bound network channel


class ResourceMode(str, Enum):
    """Lock mode for a resource acquisition."""

    EXCLUSIVE = "EXCLUSIVE"  # Mutually exclusive across all workers
    SHARED = "SHARED"  # Multiple concurrent readers permitted


@dataclass(frozen=True, slots=True)
class ResourceClaim:
    """Declaration of a resource required by a node before execution."""

    claim_id: str
    task_id: str
    node_id: str
    resource_class: ResourceClass
    target_key: str
    mode: ResourceMode

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["resource_class"] = self.resource_class.value
        d["mode"] = self.mode.value
        return d

    @property
    def composite_key(self) -> str:
        """Deterministic resource identifier used for deadlock prevention ordering."""
        return f"{self.resource_class.value}:{self.target_key}"


@dataclass(frozen=True, slots=True)
class FencingToken:
    """Monotonically increasing fencing generation token attached to every active lease."""

    resource_key: str
    owner_id: str
    generation: int
    acquired_at_utc: str
    expires_at_utc: str

    def is_expired(self, current_time_utc: str | None = None) -> bool:
        now_dt = (
            datetime.datetime.fromisoformat(current_time_utc)
            if current_time_utc
            else datetime.datetime.now(datetime.timezone.utc)
        )
        exp_dt = datetime.datetime.fromisoformat(self.expires_at_utc)
        return now_dt > exp_dt

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResourceLease:
    """Active granted lease holding a resource with an authoritative fencing token."""

    lease_id: str
    claim: ResourceClaim
    worker_id: str
    fencing_token: FencingToken

    def to_dict(self) -> dict[str, Any]:
        return {
            "lease_id": self.lease_id,
            "claim": self.claim.to_dict(),
            "worker_id": self.worker_id,
            "fencing_token": self.fencing_token.to_dict(),
        }


__all__ = [
    "FencingToken",
    "ResourceClass",
    "ResourceClaim",
    "ResourceLease",
    "ResourceMode",
]
