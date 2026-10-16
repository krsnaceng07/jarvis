"""Core data models, enums, and records for Track 2.3 Host OS Sandbox & Isolation."""

from __future__ import annotations

import dataclasses
import enum
from typing import Any

from jarvis_learning.capability.manifest import SandboxTier


class IntegrityLevel(enum.Enum):
    """Windows Mandatory Integrity Control (MIC) levels."""

    UNTRUSTED = "UNTRUSTED"  # S-1-16-0 (0x0000)
    LOW = "LOW"  # S-1-16-4096 (0x1000)
    MEDIUM = "MEDIUM"  # S-1-16-8192 (0x2000)
    HIGH = "HIGH"  # S-1-16-12288 (0x3000)
    SYSTEM = "SYSTEM"  # S-1-16-16384 (0x4000)


class EnforcementMechanism(enum.Enum):
    """Ground-truth categorization of security boundary enforcement."""

    OS_ENFORCED = "OS_ENFORCED"
    APPLICATION_ENFORCED = "APPLICATION_ENFORCED"
    SIMULATED = "SIMULATED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    NOT_TESTED = "NOT_TESTED"


class SeverityLevel(enum.Enum):
    """Escape and failure severity classification."""

    S0_EXPECTED_DENIAL = "S0_EXPECTED_DENIAL"
    S1_APP_POLICY_BYPASS = "S1_APP_POLICY_BYPASS"
    S2_SANDBOX_POLICY_VIOLATION = "S2_SANDBOX_POLICY_VIOLATION"
    S3_HOST_RESOURCE_VIOLATION = "S3_HOST_RESOURCE_VIOLATION"
    S4_UNAUTHORIZED_HOST_ACCESS = "S4_UNAUTHORIZED_HOST_ACCESS"
    S5_CREDENTIAL_EXPOSURE = "S5_CREDENTIAL_EXPOSURE"
    S6_PRIVILEGE_ESCALATION = "S6_PRIVILEGE_ESCALATION"
    S7_SANDBOX_ESCAPE = "S7_SANDBOX_ESCAPE"


class BoundaryVerdict(enum.Enum):
    """Evaluation verdict for security boundary verification."""

    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    UNVERIFIED = "UNVERIFIED"


class VectorFamily(enum.Enum):
    """Categorization of hostile boundary attack vectors."""

    TOKEN = "TOKEN"
    INTEGRITY = "INTEGRITY"
    PROCESS = "PROCESS"
    JOB = "JOB"
    FILESYSTEM = "FILESYSTEM"
    REGISTRY = "REGISTRY"
    CREDENTIAL = "CREDENTIAL"
    IPC = "IPC"
    NETWORK = "NETWORK"
    CODE = "CODE"
    PERSISTENCE = "PERSISTENCE"
    DEVICE = "DEVICE"
    BROKER = "BROKER"
    RESOURCE = "RESOURCE"
    LIFECYCLE = "LIFECYCLE"
    NEGATIVE_CONTROL = "NEGATIVE_CONTROL"


@dataclasses.dataclass(frozen=True)
class TokenStateSnapshot:
    """Comprehensive snapshot of a Windows security token."""

    user_sid: str
    username: str
    groups: list[str]
    restricted_sids: list[str]
    deny_only_sids: list[str]
    privileges: list[str]
    enabled_privileges: list[str]
    disabled_privileges: list[str]
    integrity_level: IntegrityLevel
    integrity_sid: str
    is_elevated: bool
    elevation_type: str
    has_linked_token: bool
    session_id: int
    is_restricted_token: bool

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["integrity_level"] = self.integrity_level.value
        return d


@dataclasses.dataclass(frozen=True)
class TokenDifferential:
    """Comparison diff between baseline and restricted token state."""

    stripped_privileges: list[str]
    deny_only_groups_added: list[str]
    restricted_sids_added: list[str]
    integrity_lowered: bool
    baseline_integrity: IntegrityLevel
    restricted_integrity: IntegrityLevel
    is_strictly_confined: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "stripped_privileges": self.stripped_privileges,
            "deny_only_groups_added": self.deny_only_groups_added,
            "restricted_sids_added": self.restricted_sids_added,
            "integrity_lowered": self.integrity_lowered,
            "baseline_integrity": self.baseline_integrity.value,
            "restricted_integrity": self.restricted_integrity.value,
            "is_strictly_confined": self.is_strictly_confined,
        }


@dataclasses.dataclass(frozen=True)
class HostileProbeResult:
    """Standardized outcome of a hostile attack probe."""

    vector_id: str
    family: VectorFamily
    name: str
    target: str
    attempt_details: str
    win32_error_code: int | None
    win32_error_name: str | None
    enforcement_mechanism: EnforcementMechanism
    severity: SeverityLevel
    blocked: bool
    duration_ms: float
    details: dict[str, Any] = dataclasses.field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "vector_id": self.vector_id,
            "family": self.family.value,
            "name": self.name,
            "target": self.target,
            "attempt_details": self.attempt_details,
            "win32_error_code": self.win32_error_code,
            "win32_error_name": self.win32_error_name,
            "enforcement_mechanism": self.enforcement_mechanism.value,
            "severity": self.severity.value,
            "blocked": self.blocked,
            "duration_ms": self.duration_ms,
            "details": self.details,
        }


@dataclasses.dataclass(frozen=True)
class ForensicDiffRecord:
    """Forensic before/after state diff record for an attack execution."""

    vector_id: str
    modified_files: list[str]
    modified_registry_keys: list[str]
    unauthorized_processes_spawned: list[int]
    unauthorized_handles_leaked: list[int]
    is_clean: bool

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


__all__ = [
    "BoundaryVerdict",
    "EnforcementMechanism",
    "ForensicDiffRecord",
    "HostileProbeResult",
    "IntegrityLevel",
    "SandboxTier",
    "SeverityLevel",
    "TokenDifferential",
    "TokenStateSnapshot",
    "VectorFamily",
]
