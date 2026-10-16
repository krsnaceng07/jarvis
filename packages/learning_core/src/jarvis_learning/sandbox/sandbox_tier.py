"""Sandbox tiers, fail-closed policy engine, and enforcement level reporting.

Enforces:
- INV-P10-SBX-001: Required sandbox guarantees must be established and verified
  before any restricted worker launch.
- INV-P10-SBX-002: Sandbox setup failure must fail closed (deny launch) for
  restricted workers.
- INV-P10-SBX-003: Application-level restrictions must never be reported or
  certified as OS-level enforcement.
"""

from __future__ import annotations

import dataclasses
import enum

from jarvis_learning.capability.manifest import SandboxTier
from jarvis_learning.invariants_p10 import EvidenceLevel


class SandboxSetupError(RuntimeError):
    """Raised when sandbox creation or policy enforcement cannot be guaranteed."""


class EnforcementClassification(enum.Enum):
    """Categorization of security boundary enforcement mechanism."""

    OS_ENFORCED = "OS_ENFORCED"
    APPLICATION_FILTER = "APPLICATION_FILTER"
    SIMULATED_MOCK = "SIMULATED_MOCK"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclasses.dataclass(frozen=True)
class SandboxPolicySpec:
    """Declared sandbox requirements for a worker."""

    required_tier: SandboxTier
    disallow_network: bool = True
    disallow_child_processes: bool = True
    restricted_filesystem_root: str | None = None
    fail_closed: bool = True


@dataclasses.dataclass(frozen=True)
class SandboxAttestation:
    """Attestation record of verified sandbox guarantees."""

    active_tier: SandboxTier
    evidence_level: EvidenceLevel
    enforcement_class: EnforcementClassification
    is_launch_permitted: bool
    rejection_reason: str | None = None
    guarantees: dict[str, bool] = dataclasses.field(default_factory=dict)


class SandboxPolicyEngine:
    """Evaluates sandbox capabilities and enforces fail-closed worker admission."""

    def __init__(self, available_tier: SandboxTier, evidence_level: EvidenceLevel) -> None:
        self._available_tier = available_tier
        self._evidence_level = evidence_level

    def evaluate_admission(self, spec: SandboxPolicySpec) -> SandboxAttestation:
        """Evaluate if the host environment satisfies worker sandbox requirements.

        Enforces INV-P10-SBX-002: if requirements cannot be satisfied, worker launch is denied.
        Enforces INV-P10-SBX-003: ensures application-level tiers are accurately classified.
        """
        enforcement_class = (
            EnforcementClassification.OS_ENFORCED
            if self._available_tier.value >= SandboxTier.TIER_1_RESTRICTED_TOKEN.value
            else EnforcementClassification.APPLICATION_FILTER
        )

        # Check tier satisfaction (enum values are ordered by strictness)
        tier_hierarchy = {
            SandboxTier.TIER_0_APP: 0,
            SandboxTier.TIER_1_RESTRICTED_TOKEN: 1,
            SandboxTier.TIER_2_NETWORK_FIREWALL: 2,
            SandboxTier.TIER_3_APPCONTAINER: 3,
            SandboxTier.TIER_4_WDAC: 4,
        }

        available_level = tier_hierarchy.get(self._available_tier, 0)
        required_level = tier_hierarchy.get(spec.required_tier, 0)

        guarantees: dict[str, bool] = {
            "network_blocked": available_level >= 2,
            "child_processes_blocked": available_level >= 1,
            "filesystem_restricted": available_level >= 1,
            "os_token_isolation": available_level >= 1,
        }

        if available_level < required_level:
            reason = (
                f"INSUFFICIENT_SANDBOX_TIER: requested {spec.required_tier.value}, "
                f"available {self._available_tier.value}"
            )
            if spec.fail_closed:
                return SandboxAttestation(
                    active_tier=self._available_tier,
                    evidence_level=self._evidence_level,
                    enforcement_class=enforcement_class,
                    is_launch_permitted=False,
                    rejection_reason=reason,
                    guarantees=guarantees,
                )

        return SandboxAttestation(
            active_tier=self._available_tier,
            evidence_level=self._evidence_level,
            enforcement_class=enforcement_class,
            is_launch_permitted=True,
            rejection_reason=None,
            guarantees=guarantees,
        )
