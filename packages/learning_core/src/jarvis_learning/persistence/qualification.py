"""Multi-dimensional qualification gate for Track 2.2 Reboot Persistence.

Evaluates evidence across 8 distinct dimensions and dynamically assigns evidence level:
- boot_boundary: Monotonic advance of boot session time
- filesystem_recovery: Bit-for-bit SHA-256 committed files intact, staging quarantined
- sqlite_recovery: PRAGMA integrity_check passed, WAL clean rollback
- pointer_recovery: Epoch generation valid or rolled back to verified generation
- lock_recovery: Stale pre-reboot PID locks safely reclaimed without killing live processes
- cryptographic_integrity: SHA-256 sealed, HMAC-SHA256 authenticated, event timeline unbroken
- physical_reboot: Transaction-bound causal physical machine reboot confirmed
- power_loss: External AC power loss testing (explicitly tracked as NOT_TESTED)

Strict Anti-Simulation Rule:
L6_REAL_REBOOT_SESSION requires physical_reboot and boot_boundary to be True.
Same-session validation truthfully qualifies as L4_REAL_WINDOWS_API or L3_REAL_SUBPROCESS.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from jarvis_learning.invariants_p10 import EvidenceLevel
from jarvis_learning.persistence.models import RebootVerdict


@dataclasses.dataclass(frozen=True)
class RebootQualificationDimension:
    """Status of an individual qualification dimension."""

    name: str
    qualified: bool
    status_label: str
    details: str

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass(frozen=True)
class RebootQualificationMatrix:
    """Multi-dimensional qualification gate evaluating Track 2.2 persistence evidence."""

    boot_boundary: RebootQualificationDimension
    filesystem_recovery: RebootQualificationDimension
    sqlite_recovery: RebootQualificationDimension
    pointer_recovery: RebootQualificationDimension
    lock_recovery: RebootQualificationDimension
    cryptographic_integrity: RebootQualificationDimension
    physical_reboot: RebootQualificationDimension
    power_loss: RebootQualificationDimension

    @property
    def is_physical_reboot_proven(self) -> bool:
        """True only if an actual causal physical reboot occurred for this transaction."""
        return self.boot_boundary.qualified and self.physical_reboot.qualified

    @property
    def is_durability_verified(self) -> bool:
        """True if all software persistence and recovery dimensions passed."""
        return (
            self.filesystem_recovery.qualified
            and self.sqlite_recovery.qualified
            and self.pointer_recovery.qualified
            and self.lock_recovery.qualified
            and self.cryptographic_integrity.qualified
        )

    def determine_evidence_level(self, is_subprocess: bool = False) -> EvidenceLevel:
        """Dynamically determine honest evidence classification without simulation inflation."""
        if self.is_physical_reboot_proven and self.is_durability_verified:
            return EvidenceLevel.L6_REAL_REBOOT_SESSION

        # Software durability passed on real host, but in same boot session
        if self.is_durability_verified:
            if is_subprocess:
                return EvidenceLevel.L3_REAL_SUBPROCESS
            return EvidenceLevel.L4_REAL_WINDOWS_API

        if self.filesystem_recovery.qualified or self.sqlite_recovery.qualified:
            return EvidenceLevel.L2_IN_PROCESS_INTEGRATION

        return EvidenceLevel.L0_UNTESTED

    def determine_verdict(self) -> RebootVerdict:
        """Determine overall verification verdict."""
        if not self.is_durability_verified:
            return RebootVerdict.FAIL

        # If durability passed:
        # If real reboot was intended and occurred -> PASS
        # If same session test (in-suite audit) -> PASS (with L4 qualification)
        return RebootVerdict.PASS

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_physical_reboot_proven": self.is_physical_reboot_proven,
            "is_durability_verified": self.is_durability_verified,
            "effective_evidence_level": self.determine_evidence_level().value,
            "verdict": self.determine_verdict().value,
            "dimensions": {
                "boot_boundary": self.boot_boundary.to_dict(),
                "filesystem_recovery": self.filesystem_recovery.to_dict(),
                "sqlite_recovery": self.sqlite_recovery.to_dict(),
                "pointer_recovery": self.pointer_recovery.to_dict(),
                "lock_recovery": self.lock_recovery.to_dict(),
                "cryptographic_integrity": self.cryptographic_integrity.to_dict(),
                "physical_reboot": self.physical_reboot.to_dict(),
                "power_loss": self.power_loss.to_dict(),
            },
        }

    @classmethod
    def evaluate(
        cls,
        boot_boundary_advanced: bool,
        boot_boundary_details: str,
        filesystem_ok: bool,
        filesystem_details: str,
        sqlite_ok: bool,
        sqlite_details: str,
        pointer_ok: bool,
        pointer_details: str,
        lock_ok: bool,
        lock_details: str,
        crypto_ok: bool,
        crypto_details: str,
        physical_reboot_confirmed: bool,
        physical_reboot_details: str,
    ) -> RebootQualificationMatrix:
        """Factory method to construct qualification matrix with standardized labels."""
        return cls(
            boot_boundary=RebootQualificationDimension(
                name="boot_boundary",
                qualified=boot_boundary_advanced,
                status_label="VERIFIED" if boot_boundary_advanced else "SAME_SESSION",
                details=boot_boundary_details,
            ),
            filesystem_recovery=RebootQualificationDimension(
                name="filesystem_recovery",
                qualified=filesystem_ok,
                status_label="VERIFIED" if filesystem_ok else "FAILED",
                details=filesystem_details,
            ),
            sqlite_recovery=RebootQualificationDimension(
                name="sqlite_recovery",
                qualified=sqlite_ok,
                status_label="VERIFIED" if sqlite_ok else "FAILED",
                details=sqlite_details,
            ),
            pointer_recovery=RebootQualificationDimension(
                name="pointer_recovery",
                qualified=pointer_ok,
                status_label="VERIFIED" if pointer_ok else "FAILED",
                details=pointer_details,
            ),
            lock_recovery=RebootQualificationDimension(
                name="lock_recovery",
                qualified=lock_ok,
                status_label="VERIFIED" if lock_ok else "FAILED",
                details=lock_details,
            ),
            cryptographic_integrity=RebootQualificationDimension(
                name="cryptographic_integrity",
                qualified=crypto_ok,
                status_label="VERIFIED" if crypto_ok else "FAILED",
                details=crypto_details,
            ),
            physical_reboot=RebootQualificationDimension(
                name="physical_reboot",
                qualified=physical_reboot_confirmed,
                status_label="CONFIRMED" if physical_reboot_confirmed else "NOT_PERFORMED",
                details=physical_reboot_details,
            ),
            power_loss=RebootQualificationDimension(
                name="power_loss",
                qualified=False,
                status_label="NOT_TESTED",
                details="Physical AC power loss requires external relay hardware; pending Track 2.2C harness",
            ),
        )


__all__ = [
    "RebootQualificationDimension",
    "RebootQualificationMatrix",
]
