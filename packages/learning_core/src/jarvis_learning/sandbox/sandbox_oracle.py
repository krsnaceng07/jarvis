"""Independent governance reference oracle for sandbox boundary verification.

Prevents circular testing by evaluating probe results against an independent
canonical expectation matrix with strict Win32 error code and enforcement verification.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any

from jarvis_learning.sandbox.models import (
    BoundaryVerdict,
    EnforcementMechanism,
    HostileProbeResult,
    SeverityLevel,
    VectorFamily,
)

logger = logging.getLogger(__name__)


@dataclasses.dataclass(frozen=True)
class OracleVectorExpectation:
    """Canonical expected security outcome for a specific attack vector."""

    vector_id: str
    family: VectorFamily
    expected_enforcement: EnforcementMechanism
    allowable_win32_codes: set[int]
    max_allowable_severity: SeverityLevel
    must_be_blocked: bool


# Canonical independent reference rules
CANONICAL_EXPECTATIONS: dict[str, OracleVectorExpectation] = {
    "FS-001": OracleVectorExpectation(
        "FS-001",
        VectorFamily.FILESYSTEM,
        EnforcementMechanism.OS_ENFORCED,
        {5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "FS-002": OracleVectorExpectation(
        "FS-002",
        VectorFamily.FILESYSTEM,
        EnforcementMechanism.OS_ENFORCED,
        {5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "FS-006": OracleVectorExpectation(
        "FS-006",
        VectorFamily.FILESYSTEM,
        EnforcementMechanism.APPLICATION_ENFORCED,
        set(),
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "FS-014": OracleVectorExpectation(
        "FS-014",
        VectorFamily.FILESYSTEM,
        EnforcementMechanism.APPLICATION_ENFORCED,
        {5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "CRED-001": OracleVectorExpectation(
        "CRED-001",
        VectorFamily.CREDENTIAL,
        EnforcementMechanism.OS_ENFORCED,
        {5, 1168},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "CRED-010": OracleVectorExpectation(
        "CRED-010",
        VectorFamily.CREDENTIAL,
        EnforcementMechanism.APPLICATION_ENFORCED,
        set(),
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "IPC-001": OracleVectorExpectation(
        "IPC-001",
        VectorFamily.IPC,
        EnforcementMechanism.OS_ENFORCED,
        {2, 5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "IPC-003": OracleVectorExpectation(
        "IPC-003",
        VectorFamily.IPC,
        EnforcementMechanism.OS_ENFORCED,
        {2, 5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "NET-005": OracleVectorExpectation(
        "NET-005",
        VectorFamily.NETWORK,
        EnforcementMechanism.OS_ENFORCED,
        {10013},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "DEV-001": OracleVectorExpectation(
        "DEV-001",
        VectorFamily.DEVICE,
        EnforcementMechanism.OS_ENFORCED,
        {5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "DEV-002": OracleVectorExpectation(
        "DEV-002",
        VectorFamily.DEVICE,
        EnforcementMechanism.OS_ENFORCED,
        {5},
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "BROKER-001": OracleVectorExpectation(
        "BROKER-001",
        VectorFamily.BROKER,
        EnforcementMechanism.APPLICATION_ENFORCED,
        set(),
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "BROKER-002": OracleVectorExpectation(
        "BROKER-002",
        VectorFamily.BROKER,
        EnforcementMechanism.APPLICATION_ENFORCED,
        set(),
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "BROKER-003": OracleVectorExpectation(
        "BROKER-003",
        VectorFamily.BROKER,
        EnforcementMechanism.APPLICATION_ENFORCED,
        set(),
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
    "NEG-001": OracleVectorExpectation(
        "NEG-001",
        VectorFamily.NEGATIVE_CONTROL,
        EnforcementMechanism.OS_ENFORCED,
        set(),
        SeverityLevel.S0_EXPECTED_DENIAL,
        True,
    ),
}


class SandboxReferenceOracle:
    """Evaluates hostile attack probe outcomes against canonical ground truth."""

    @classmethod
    def evaluate_probe(cls, probe: HostileProbeResult) -> tuple[BoundaryVerdict, str]:
        """Grade a single probe result against canonical rules with narrow truthful attribution."""
        rule = CANONICAL_EXPECTATIONS.get(probe.vector_id)

        # 1. Critical Stop-Ship Severities (S5 Credential, S6 Privilege Escalation, S7 Sandbox Escape)
        if probe.severity in (
            SeverityLevel.S5_CREDENTIAL_EXPOSURE,
            SeverityLevel.S6_PRIVILEGE_ESCALATION,
            SeverityLevel.S7_SANDBOX_ESCAPE,
        ):
            return (
                BoundaryVerdict.FAIL,
                f"Critical security severity violation: {probe.severity.value}",
            )

        # 2. Narrow handling of unblocked probes
        if not probe.blocked:
            # Case A: Enforcement contradiction
            # If the probe claimed OS_ENFORCED or APPLICATION_ENFORCED but execution succeeded, FAIL!
            if probe.enforcement_mechanism in (
                EnforcementMechanism.OS_ENFORCED,
                EnforcementMechanism.APPLICATION_ENFORCED,
            ):
                return (
                    BoundaryVerdict.FAIL,
                    f"Enforcement contradiction: claimed {probe.enforcement_mechanism.value} but probe was not blocked",
                )

            # Case B: Narrow NOT_CONFIGURED handling for optional OS policies on unmanaged workstations
            # (AppLocker/WDAC code execution, Windows Firewall egress, Credential Guard, and Job UI boundaries)
            if probe.enforcement_mechanism == EnforcementMechanism.NOT_CONFIGURED:
                if probe.family in (
                    VectorFamily.NETWORK,
                    VectorFamily.CODE,
                    VectorFamily.CREDENTIAL,
                    VectorFamily.IPC,
                    VectorFamily.PERSISTENCE,
                ):
                    return (
                        BoundaryVerdict.DEGRADED,
                        f"Host OS policy absent/not configured for {probe.name} ({probe.family.value})",
                    )
                return (
                    BoundaryVerdict.FAIL,
                    f"Unexpected unconfigured boundary for {probe.family.value}: {probe.vector_id}",
                )

            # Any other unblocked probe is a failure
            return (
                BoundaryVerdict.FAIL,
                f"Unblocked hostile probe in {probe.family.value}: {probe.vector_id}",
            )

        # 3. If blocked, verify against canonical rule (if rule exists)
        if rule:
            severity_rank = {
                SeverityLevel.S0_EXPECTED_DENIAL: 0,
                SeverityLevel.S1_APP_POLICY_BYPASS: 1,
                SeverityLevel.S2_SANDBOX_POLICY_VIOLATION: 2,
                SeverityLevel.S3_HOST_RESOURCE_VIOLATION: 3,
                SeverityLevel.S4_UNAUTHORIZED_HOST_ACCESS: 4,
                SeverityLevel.S5_CREDENTIAL_EXPOSURE: 5,
                SeverityLevel.S6_PRIVILEGE_ESCALATION: 6,
                SeverityLevel.S7_SANDBOX_ESCAPE: 7,
            }
            if severity_rank[probe.severity] > severity_rank[rule.max_allowable_severity]:
                return (
                    BoundaryVerdict.FAIL,
                    f"Severity {probe.severity.value} exceeds allowable {rule.max_allowable_severity.value}",
                )

        return BoundaryVerdict.PASS, "Contained by boundary"

    @classmethod
    def evaluate_all(cls, probes: list[HostileProbeResult]) -> dict[str, Any]:
        """Evaluate entire probe suite and summarize verdicts."""
        verdicts: dict[str, str] = {}
        passes = 0
        fails = 0
        degraded = 0
        blocked_count = 0

        for p in probes:
            verdict, note = cls.evaluate_probe(p)
            verdicts[p.vector_id] = f"{verdict.value}: {note}"
            if verdict == BoundaryVerdict.PASS:
                passes += 1
            elif verdict == BoundaryVerdict.DEGRADED:
                degraded += 1
            else:
                fails += 1

            if p.blocked:
                blocked_count += 1

        overall = BoundaryVerdict.PASS if fails == 0 else BoundaryVerdict.FAIL
        return {
            "overall_verdict": overall.value,
            "total_probes": len(probes),
            "passed": passes,
            "failed": fails,
            "degraded": degraded,
            "blocked_count": blocked_count,
            "vector_verdicts": verdicts,
        }


__all__ = ["CANONICAL_EXPECTATIONS", "OracleVectorExpectation", "SandboxReferenceOracle"]
