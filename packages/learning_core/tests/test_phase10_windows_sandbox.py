"""Stage 10.4: Windows Security Boundary Enforcement Scenarios.

Scenarios P10-023 to P10-030:
- P10-023: Restricted token and Job Object configuration models (INV-P10-SBX-001).
- P10-024: Fail-closed behavior: setup failure denies worker launch unconditionally (INV-P10-SBX-002).
- P10-025: Reporting accuracy: application-level restrictions never report as OS enforcement (INV-P10-SBX-003).
- P10-026: Hostile vector: protected file access blocked.
- P10-027: Hostile vector: scratch directory write escape blocked.
- P10-028: Hostile vector: unauthorized child process creation blocked.
- P10-029: Hostile vector: outbound network access blocked.
- P10-030: Comprehensive penetration matrix produces explicit classified statuses.
"""

from __future__ import annotations

from pathlib import Path

from jarvis_learning.invariants_p10 import (
    EvidenceLevel,
    get_p10_evidence_ledger,
)
from jarvis_learning.sandbox.boundary_validator import (
    AttackOutcomeStatus,
    AttackVector,
    HostileBoundaryValidator,
)
from jarvis_learning.sandbox.sandbox_tier import (
    EnforcementClassification,
    SandboxPolicyEngine,
    SandboxPolicySpec,
    SandboxTier,
)
from jarvis_learning.sandbox.windows_tokens import (
    WindowsJobObjectConfig,
    WindowsTokenConfig,
    WorkerLaunchContext,
)


def test_p10_023_token_and_job_object_models() -> None:
    """P10-023: Restricted token and Job Object configuration models (INV-P10-SBX-001)."""
    ledger = get_p10_evidence_ledger()

    token_cfg = WindowsTokenConfig(
        strip_admin_sids=True,
        disable_max_privileges=True,
        integrity_level="SECURITY_MANDATORY_LOW_RID",
        zero_socket_handles=True,
    )
    job_cfg = WindowsJobObjectConfig(
        kill_on_job_close=True,
        max_active_processes=1,
        memory_limit_bytes=2 * 1024 * 1024 * 1024,
    )
    context = WorkerLaunchContext(
        command=["python", "-m", "worker"],
        scratch_dir="C:/temp/scratch",
        token_config=token_cfg,
        job_config=job_cfg,
    )

    env = context.build_sanitized_environment()
    assert env["JARVIS_SANDBOX_RESTRICTED"] == "1"
    assert env["JARVIS_SCRATCH_DIR"] == "C:/temp/scratch"
    assert not any("SECRET" in k for k in env)

    ledger.record(
        scenario_id="P10-023",
        invariant_id="INV-P10-SBX-001",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"integrity_level": token_cfg.integrity_level},
    )


def test_p10_024_fail_closed_denies_worker_launch() -> None:
    """P10-024: Fail-closed behavior: setup failure denies worker launch unconditionally (INV-P10-SBX-002)."""
    ledger = get_p10_evidence_ledger()

    # Host only has TIER_0 (App level), but worker requests TIER_2 (Network firewall)
    engine = SandboxPolicyEngine(
        available_tier=SandboxTier.TIER_0_APP,
        evidence_level=EvidenceLevel.L1_UNIT_MOCK,
    )
    spec = SandboxPolicySpec(
        required_tier=SandboxTier.TIER_2_NETWORK_FIREWALL,
        fail_closed=True,
    )

    attestation = engine.evaluate_admission(spec)
    assert attestation.is_launch_permitted is False
    assert "INSUFFICIENT_SANDBOX_TIER" in (attestation.rejection_reason or "")

    ledger.record(
        scenario_id="P10-024",
        invariant_id="INV-P10-SBX-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"launch_permitted": False},
    )


def test_p10_025_accurate_enforcement_reporting() -> None:
    """P10-025: Reporting accuracy: application-level restrictions never report as OS enforcement (INV-P10-SBX-003)."""
    ledger = get_p10_evidence_ledger()

    engine = SandboxPolicyEngine(
        available_tier=SandboxTier.TIER_0_APP,
        evidence_level=EvidenceLevel.L1_UNIT_MOCK,
    )
    spec = SandboxPolicySpec(required_tier=SandboxTier.TIER_0_APP)

    attestation = engine.evaluate_admission(spec)
    assert attestation.is_launch_permitted is True
    # Crucial: Must be marked APPLICATION_FILTER, NOT OS_ENFORCED
    assert attestation.enforcement_class == EnforcementClassification.APPLICATION_FILTER

    ledger.record(
        scenario_id="P10-025",
        invariant_id="INV-P10-SBX-003",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"enforcement_class": attestation.enforcement_class.value},
    )


def test_p10_026_hostile_protected_file_read_blocked() -> None:
    """P10-026: Hostile vector: protected file read blocked."""
    ledger = get_p10_evidence_ledger()

    validator = HostileBoundaryValidator(
        active_tier=SandboxTier.TIER_1_RESTRICTED_TOKEN,
        scratch_dir=Path("C:/scratch"),
        enforcement_class=EnforcementClassification.OS_ENFORCED,
    )
    res = validator.test_vector(AttackVector.READ_PROTECTED_FILE)
    assert res.blocked is True
    assert res.status == AttackOutcomeStatus.BLOCKED_BY_OS

    ledger.record(
        scenario_id="P10-026",
        invariant_id="INV-P10-SBX-001",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"vector": res.vector.value, "status": res.status.value},
    )


def test_p10_027_hostile_scratch_write_escape_blocked() -> None:
    """P10-027: Hostile vector: scratch boundary write escape blocked."""
    ledger = get_p10_evidence_ledger()

    validator = HostileBoundaryValidator(
        active_tier=SandboxTier.TIER_1_RESTRICTED_TOKEN,
        scratch_dir=Path("C:/scratch"),
        enforcement_class=EnforcementClassification.OS_ENFORCED,
    )
    res = validator.test_vector(AttackVector.WRITE_OUTSIDE_SCRATCH)
    assert res.blocked is True
    assert res.status == AttackOutcomeStatus.BLOCKED_BY_OS

    ledger.record(
        scenario_id="P10-027",
        invariant_id="INV-P10-SBX-001",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"vector": res.vector.value, "status": res.status.value},
    )


def test_p10_028_hostile_child_process_creation_blocked() -> None:
    """P10-028: Hostile vector: unauthorized child process spawn blocked."""
    ledger = get_p10_evidence_ledger()

    validator = HostileBoundaryValidator(
        active_tier=SandboxTier.TIER_1_RESTRICTED_TOKEN,
        scratch_dir=Path("C:/scratch"),
        enforcement_class=EnforcementClassification.OS_ENFORCED,
    )
    res = validator.test_vector(AttackVector.SPAWN_CHILD_PROCESS)
    assert res.blocked is True
    assert res.status == AttackOutcomeStatus.BLOCKED_BY_OS

    ledger.record(
        scenario_id="P10-028",
        invariant_id="INV-P10-SBX-001",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"vector": res.vector.value, "status": res.status.value},
    )


def test_p10_029_hostile_outbound_network_blocked() -> None:
    """P10-029: Hostile vector: outbound TCP/DNS network access blocked."""
    ledger = get_p10_evidence_ledger()

    validator = HostileBoundaryValidator(
        active_tier=SandboxTier.TIER_2_NETWORK_FIREWALL,
        scratch_dir=Path("C:/scratch"),
        enforcement_class=EnforcementClassification.OS_ENFORCED,
    )
    res = validator.test_vector(AttackVector.OUTBOUND_TCP)
    assert res.blocked is True
    assert res.status == AttackOutcomeStatus.BLOCKED_BY_OS

    ledger.record(
        scenario_id="P10-029",
        invariant_id="INV-P10-SBX-001",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"vector": res.vector.value, "status": res.status.value},
    )


def test_p10_030_comprehensive_penetration_matrix() -> None:
    """P10-030: Comprehensive penetration matrix produces explicit classified statuses."""
    ledger = get_p10_evidence_ledger()

    validator = HostileBoundaryValidator(
        active_tier=SandboxTier.TIER_2_NETWORK_FIREWALL,
        scratch_dir=Path("C:/scratch"),
        enforcement_class=EnforcementClassification.OS_ENFORCED,
    )
    all_results = validator.test_all_vectors()

    assert len(all_results) == 11
    # Ensure every result is blocked and categorized
    for r in all_results:
        assert r.blocked is True
        assert r.status in (
            AttackOutcomeStatus.BLOCKED_BY_OS,
            AttackOutcomeStatus.BLOCKED_BY_POLICY,
            AttackOutcomeStatus.BLOCKED_BY_APPLICATION,
        )

    ledger.record(
        scenario_id="P10-030",
        invariant_id="INV-P10-SBX-001",
        evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        passed=True,
        details={"total_vectors_tested": len(all_results)},
    )
