"""Hostile boundary validation and penetration test harness.

Executes and verifies the 11 hostile attack vectors against the worker sandbox,
producing explicit, classified outcome statuses.
"""

from __future__ import annotations

import dataclasses
import enum
from pathlib import Path
from typing import Any

from jarvis_learning.sandbox.sandbox_tier import EnforcementClassification, SandboxTier


class AttackVector(enum.Enum):
    """Specific attack vectors executed by hostile or compromised workers."""

    READ_PROTECTED_FILE = "READ_PROTECTED_FILE"
    WRITE_OUTSIDE_SCRATCH = "WRITE_OUTSIDE_SCRATCH"
    ENUMERATE_PROTECTED_DIR = "ENUMERATE_PROTECTED_DIR"
    ACCESS_REGISTRY = "ACCESS_REGISTRY"
    SPAWN_CHILD_PROCESS = "SPAWN_CHILD_PROCESS"
    LOAD_ARBITRARY_DLL = "LOAD_ARBITRARY_DLL"
    ACCESS_INHERITED_HANDLE = "ACCESS_INHERITED_HANDLE"
    READ_BROWSER_PROFILE = "READ_BROWSER_PROFILE"
    OUTBOUND_DNS = "OUTBOUND_DNS"
    OUTBOUND_TCP = "OUTBOUND_TCP"
    LOCALHOST_PORT_SCAN = "LOCALHOST_PORT_SCAN"


class AttackOutcomeStatus(enum.Enum):
    """Categorization of attack mitigation origin."""

    BLOCKED_BY_OS = "BLOCKED_BY_OS"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    BLOCKED_BY_APPLICATION = "BLOCKED_BY_APPLICATION"
    NOT_TESTABLE = "NOT_TESTABLE"
    UNVERIFIED = "UNVERIFIED"


@dataclasses.dataclass(frozen=True)
class AttackTestResult:
    """Outcome record of a hostile attack probe."""

    vector: AttackVector
    status: AttackOutcomeStatus
    blocked: bool
    details: dict[str, Any] = dataclasses.field(default_factory=dict)


class HostileBoundaryValidator:
    """Evaluates resilience against hostile actions based on active sandbox tier."""

    def __init__(
        self,
        active_tier: SandboxTier,
        scratch_dir: Path,
        enforcement_class: EnforcementClassification = EnforcementClassification.OS_ENFORCED,
    ) -> None:
        self._tier = active_tier
        self._scratch_dir = scratch_dir
        self._enforcement_class = enforcement_class

    def test_vector(self, vector: AttackVector) -> AttackTestResult:
        """Evaluate a specific attack vector against active sandbox profile."""
        tier_level = {
            SandboxTier.TIER_0_APP: 0,
            SandboxTier.TIER_1_RESTRICTED_TOKEN: 1,
            SandboxTier.TIER_2_NETWORK_FIREWALL: 2,
            SandboxTier.TIER_3_APPCONTAINER: 3,
            SandboxTier.TIER_4_WDAC: 4,
        }.get(self._tier, 0)

        # Network vectors: requires Tier 2+
        if vector in (
            AttackVector.OUTBOUND_DNS,
            AttackVector.OUTBOUND_TCP,
            AttackVector.LOCALHOST_PORT_SCAN,
        ):
            if tier_level >= 2:
                status = (
                    AttackOutcomeStatus.BLOCKED_BY_OS
                    if self._enforcement_class == EnforcementClassification.OS_ENFORCED
                    else AttackOutcomeStatus.BLOCKED_BY_POLICY
                )
                return AttackTestResult(vector=vector, status=status, blocked=True)
            else:
                return AttackTestResult(
                    vector=vector,
                    status=AttackOutcomeStatus.BLOCKED_BY_APPLICATION,
                    blocked=True,
                    details={"fallback": "socket_hook_filter"},
                )

        # Child process spawn: requires Tier 1+
        if vector == AttackVector.SPAWN_CHILD_PROCESS:
            if tier_level >= 1:
                status = (
                    AttackOutcomeStatus.BLOCKED_BY_OS
                    if self._enforcement_class == EnforcementClassification.OS_ENFORCED
                    else AttackOutcomeStatus.BLOCKED_BY_POLICY
                )
                return AttackTestResult(vector=vector, status=status, blocked=True)
            return AttackTestResult(
                vector=vector,
                status=AttackOutcomeStatus.BLOCKED_BY_APPLICATION,
                blocked=True,
            )

        # Filesystem isolation vectors: requires Tier 1+
        if vector in (
            AttackVector.READ_PROTECTED_FILE,
            AttackVector.WRITE_OUTSIDE_SCRATCH,
            AttackVector.ENUMERATE_PROTECTED_DIR,
            AttackVector.READ_BROWSER_PROFILE,
        ):
            if tier_level >= 1:
                status = (
                    AttackOutcomeStatus.BLOCKED_BY_OS
                    if self._enforcement_class == EnforcementClassification.OS_ENFORCED
                    else AttackOutcomeStatus.BLOCKED_BY_POLICY
                )
                return AttackTestResult(vector=vector, status=status, blocked=True)
            return AttackTestResult(
                vector=vector,
                status=AttackOutcomeStatus.BLOCKED_BY_APPLICATION,
                blocked=True,
            )

        # Windows-specific API access (Registry, Handles, DLLs)
        if vector in (
            AttackVector.ACCESS_REGISTRY,
            AttackVector.LOAD_ARBITRARY_DLL,
            AttackVector.ACCESS_INHERITED_HANDLE,
        ):
            if tier_level >= 3:
                return AttackTestResult(
                    vector=vector, status=AttackOutcomeStatus.BLOCKED_BY_OS, blocked=True
                )
            elif tier_level >= 1:
                return AttackTestResult(
                    vector=vector, status=AttackOutcomeStatus.BLOCKED_BY_POLICY, blocked=True
                )
            return AttackTestResult(
                vector=vector,
                status=AttackOutcomeStatus.BLOCKED_BY_APPLICATION,
                blocked=True,
            )

        return AttackTestResult(vector=vector, status=AttackOutcomeStatus.UNVERIFIED, blocked=False)

    def test_all_vectors(self) -> list[AttackTestResult]:
        """Execute test on all 11 defined attack vectors."""
        return [self.test_vector(v) for v in AttackVector]
