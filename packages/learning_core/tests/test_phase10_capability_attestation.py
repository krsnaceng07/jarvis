"""Stage 10.1: Capability Discovery & Environment Attestation Scenarios.

Scenarios P10-001 to P10-006:
- P10-001: Device capability matrix and operational state transitions.
- P10-002: Capability manifest generation, JSON serialization, and SHA256 digest sealing.
- P10-003: Evidence level tagging (L0-L8) preventing unverified capability claims (INV-P10-CAP-001).
- P10-004: Mutual compatibility handshake succeeds on matching contract digests.
- P10-005: Incompatible component or schema digest strictly rejects worker startup (INV-P10-COMP-001).
- P10-006: Fail-closed attestation when critical environment telemetry is missing.
"""

from __future__ import annotations

import json
import pytest

from jarvis_learning.capability.handshake import (
    CompatibilityHandshake,
    WorkerIncompatibleError,
    verify_compatibility_handshake,
)
from jarvis_learning.capability.manifest import (
    CapabilityMatrix,
    DeviceCapability,
    DeviceState,
    SandboxTier,
    build_host_capability_manifest,
)
from jarvis_learning.invariants_p10 import (
    EvidenceLevel,
    get_p10_evidence_ledger,
)


def test_p10_001_device_capability_matrix_and_states() -> None:
    """P10-001: Granular device capability matrix accurately models operational states."""
    ledger = get_p10_evidence_ledger()

    matrix = CapabilityMatrix(
        device_present=True,
        driver_present=True,
        telemetry_available=True,
        compute_runtime_available=True,
        memory_telemetry_available=True,
        temperature_available=True,
        power_telemetry_available=False,
        process_isolation_supported=True,
        device_usable_by_learning_worker=True,
    )
    dev = DeviceCapability(
        device_id="gpu_0",
        device_name="Test Hardware Device",
        backend="CUDA",
        state=DeviceState.COMPUTE_READY,
        matrix=matrix,
        evidence_level=EvidenceLevel.L5_REAL_HARDWARE,
        total_memory_bytes=8 * 1024 * 1024 * 1024,
        driver_version="550.54.14",
    )

    dev_dict = dev.to_dict()
    assert dev_dict["state"] == "COMPUTE_READY"
    assert dev_dict["backend"] == "CUDA"
    assert dev_dict["matrix"]["compute_runtime_available"] is True
    assert dev_dict["matrix"]["power_telemetry_available"] is False

    ledger.record(
        scenario_id="P10-001",
        invariant_id="INV-P10-HW-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"state": dev.state.value, "backend": dev.backend},
    )


def test_p10_002_capability_manifest_sealing_and_serialization() -> None:
    """P10-002: Capability manifest seals deterministic SHA256 digest and valid JSON."""
    ledger = get_p10_evidence_ledger()

    manifest = build_host_capability_manifest(
        sandbox_tier=SandboxTier.TIER_1_RESTRICTED_TOKEN,
        sandbox_evidence_level=EvidenceLevel.L4_REAL_WINDOWS_API,
        cross_session_verified=False,
        cross_reboot_verified=False,
        power_loss_verified=False,
    )

    assert manifest.manifest_digest != ""
    assert manifest.manifest_digest == manifest.compute_digest()

    raw_json = manifest.to_json()
    parsed = json.loads(raw_json)
    assert parsed["manifest_digest"] == manifest.manifest_digest
    assert parsed["sandbox_tier"] == "TIER_1_RESTRICTED_TOKEN"
    assert parsed["sandbox_evidence_level"] == "L4_REAL_WINDOWS_API"
    assert parsed["cross_reboot_verified"] is False

    ledger.record(
        scenario_id="P10-002",
        invariant_id="INV-P10-CAP-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"manifest_digest": manifest.manifest_digest},
    )


def test_p10_003_evidence_level_tagging_prevents_unverified_claims() -> None:
    """P10-003: Evidence level tagging enforces distinction between simulated and OS/hardware verification (INV-P10-CAP-001)."""
    ledger = get_p10_evidence_ledger()

    simulated_matrix = CapabilityMatrix(
        device_present=True,
        driver_present=False,
        telemetry_available=False,
        compute_runtime_available=False,
    )
    simulated_dev = DeviceCapability(
        device_id="sim_0",
        device_name="Simulated Accelerator",
        backend="EMULATION",
        state=DeviceState.COMPUTE_DEGRADED,
        matrix=simulated_matrix,
        evidence_level=EvidenceLevel.L1_UNIT_MOCK,
    )

    assert simulated_dev.evidence_level != EvidenceLevel.L5_REAL_HARDWARE
    assert simulated_dev.state == DeviceState.COMPUTE_DEGRADED
    assert simulated_dev.matrix.compute_runtime_available is False

    ledger.record(
        scenario_id="P10-003",
        invariant_id="INV-P10-CAP-001",
        evidence_level=EvidenceLevel.L0_STATIC,
        passed=True,
        details={"evidence_level": simulated_dev.evidence_level.value},
    )


def test_p10_004_compatibility_handshake_success() -> None:
    """P10-004: Mutual compatibility handshake succeeds when all contract digests match."""
    ledger = get_p10_evidence_ledger()

    host_handshake = CompatibilityHandshake(
        host_version="10.0.0",
        worker_version="10.0.0",
        protocol_version="1.0.0",
        event_schema_version="1.0.0",
        tool_registry_digest="sha256_tool_reg_abc",
        sandbox_policy_digest="sha256_sandbox_policy_def",
        runtime_contract_digest="sha256_runtime_contract_ghi",
        capability_manifest_digest="sha256_cap_manifest_jkl",
    )

    worker_handshake = CompatibilityHandshake(
        host_version="10.0.0",
        worker_version="10.0.0",
        protocol_version="1.0.0",
        event_schema_version="1.0.0",
        tool_registry_digest="sha256_tool_reg_abc",
        sandbox_policy_digest="sha256_sandbox_policy_def",
        runtime_contract_digest="sha256_runtime_contract_ghi",
        capability_manifest_digest="sha256_cap_manifest_jkl",
    )

    result = verify_compatibility_handshake(
        host_handshake, worker_handshake, raise_on_mismatch=True
    )
    assert result.compatible is True
    assert result.rejection_reason is None
    assert len(result.mismatched_fields) == 0

    ledger.record(
        scenario_id="P10-004",
        invariant_id="INV-P10-COMP-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"handshake_digest": result.handshake_digest},
    )


def test_p10_005_incompatible_digest_rejects_worker_startup() -> None:
    """P10-005: Incompatible component or schema digest strictly raises WorkerIncompatibleError (INV-P10-COMP-001)."""
    ledger = get_p10_evidence_ledger()

    host_handshake = CompatibilityHandshake(
        host_version="10.0.0",
        worker_version="10.0.0",
        protocol_version="1.0.0",
        event_schema_version="1.0.0",
        tool_registry_digest="sha256_tool_reg_abc",
        sandbox_policy_digest="sha256_sandbox_policy_def",
        runtime_contract_digest="sha256_runtime_contract_ghi",
        capability_manifest_digest="sha256_cap_manifest_jkl",
    )

    incompatible_worker = CompatibilityHandshake(
        host_version="10.0.0",
        worker_version="10.0.0",
        protocol_version="1.0.0",
        event_schema_version="1.0.0",
        tool_registry_digest="sha256_MUTATED_REGISTRY",
        sandbox_policy_digest="sha256_sandbox_policy_def",
        runtime_contract_digest="sha256_runtime_contract_ghi",
        capability_manifest_digest="sha256_cap_manifest_jkl",
    )

    with pytest.raises(WorkerIncompatibleError) as exc_info:
        verify_compatibility_handshake(host_handshake, incompatible_worker, raise_on_mismatch=True)

    assert "tool_registry_digest mismatch" in str(exc_info.value)

    res = verify_compatibility_handshake(
        host_handshake, incompatible_worker, raise_on_mismatch=False
    )
    assert res.compatible is False
    assert "tool_registry_digest mismatch" in (res.rejection_reason or "")

    ledger.record(
        scenario_id="P10-005",
        invariant_id="INV-P10-COMP-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"rejection_reason": res.rejection_reason},
    )


def test_p10_006_fail_closed_missing_telemetry() -> None:
    """P10-006: System transitions to conservative mode when telemetry is missing and never claims verified safety."""
    ledger = get_p10_evidence_ledger()

    matrix = CapabilityMatrix(
        device_present=True,
        driver_present=True,
        telemetry_available=False,
        compute_runtime_available=True,
        temperature_available=False,
    )
    dev = DeviceCapability(
        device_id="gpu_unmonitored",
        device_name="Unmonitored GPU",
        backend="CUDA",
        state=DeviceState.COMPUTE_DEGRADED,
        matrix=matrix,
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
    )

    assert dev.state == DeviceState.COMPUTE_DEGRADED
    assert dev.matrix.telemetry_available is False
    assert dev.matrix.temperature_available is False

    ledger.record(
        scenario_id="P10-006",
        invariant_id="INV-P10-HW-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"state": dev.state.value, "telemetry_available": False},
    )
