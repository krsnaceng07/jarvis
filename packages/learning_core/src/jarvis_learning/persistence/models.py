"""Core data models, enums, and records for Track 2.2 Reboot Persistence."""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from jarvis_learning.invariants_p10 import EvidenceLevel


class RebootReality(enum.Enum):
    """Ground-truth reality of the observed reboot boundary."""

    REAL_REBOOT = "REAL_REBOOT"
    SAME_SESSION = "SAME_SESSION"
    SIMULATION_VALIDATION = "SIMULATION_VALIDATION"
    UNVERIFIED = "UNVERIFIED"


class RebootVerdict(enum.Enum):
    """Formal evaluation verdict for reboot persistence tests."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class DurabilityLevel(enum.Enum):
    """Classification of filesystem and database durability guarantees."""

    MEMORY_ONLY = "MEMORY_ONLY"
    USERSPACE_FLUSHED = "USERSPACE_FLUSHED"
    OS_FLUSHED = "OS_FLUSHED"
    ATOMIC_RENAME = "ATOMIC_RENAME"
    DATABASE_COMMITTED = "DATABASE_COMMITTED"
    VERIFIED_AFTER_REBOOT = "VERIFIED_AFTER_REBOOT"


class TransactionState(enum.Enum):
    """Lifecycle states for an individual reboot validation transaction."""

    CREATED = "CREATED"
    ARMED = "ARMED"
    REBOOT_CONFIRMED = "REBOOT_CONFIRMED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    ORPHANED = "ORPHANED"
    FAILED = "FAILED"


@dataclasses.dataclass(frozen=True)
class QuarantineRecord:
    """Forensic audit record of a quarantined broken or uncommitted artifact."""

    original_path: str
    quarantined_path: str
    file_size_bytes: int
    sha256_digest: str
    reason: str
    quarantined_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class PointerState:
    """Schema for the active pointer with epoch generation and transaction binding."""

    generation: int
    artifact_id: str
    sha256: str
    committed_at_utc: str
    transaction_id: str
    state: str = "COMMITTED"

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


__all__ = [
    "DurabilityLevel",
    "EvidenceLevel",
    "PointerState",
    "QuarantineRecord",
    "RebootReality",
    "RebootVerdict",
    "TransactionState",
]
