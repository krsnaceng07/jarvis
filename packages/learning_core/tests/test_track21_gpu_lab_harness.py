"""Comprehensive verification suite for Track 2.1 GPU Hardware Laboratory Validation Harness.

Tests layered discovery, provenance tracking, telemetry freshness policy, active voice
headroom probing, independent reference oracle, thermal replay, run locks, hash chaining,
cryptographic attestation, and strict 10-point L5 qualification rules.
"""

from __future__ import annotations

import pathlib
import time

import pytest

from jarvis_learning.hardware.backend_adapters.cpu_adapter import CpuBackendAdapter
from jarvis_learning.hardware.backend_adapters.cuda_adapter import CudaBackendAdapter
from jarvis_learning.hardware.backend_adapters.directml_adapter import DirectMLBackendAdapter
from jarvis_learning.hardware.device_discovery import LayeredDiscoveryEngine
from jarvis_learning.hardware.evidence_integrity import (
    EvidenceIntegritySealer,
    L5QualificationChecklist,
)
from jarvis_learning.hardware.evidence_schema import EventHashChain
from jarvis_learning.hardware.fault_injection import GPUFaultInjector
from jarvis_learning.hardware.governance_reference import GovernanceReferenceModel
from jarvis_learning.hardware.gpu_lab_harness import GPULabConfig, GPULabHarness
from jarvis_learning.hardware.memory_probe import ActiveVoiceHeadroomProber, MemoryProbeEngine
from jarvis_learning.hardware.models import (
    DeviceType,
    EvidenceLevel,
    FallbackReason,
    HardwareReality,
    MemoryAccounting,
    TelemetryQuality,
    TestVerdict,
)
from jarvis_learning.hardware.permissions import PermissionInspector
from jarvis_learning.hardware.provenance import ProvenanceValue
from jarvis_learning.hardware.recovery_validator import RecoveryValidator
from jarvis_learning.hardware.run_lock import LabRunConflictError, SingleInstanceRunLock
from jarvis_learning.hardware.telemetry import TelemetryCollector
from jarvis_learning.hardware.telemetry_quality import TelemetryQualityValidator
from jarvis_learning.hardware.thermal_replay import ThermalReplayEngine


def test_models_and_enums() -> None:
    """Verify core enums and accounting structures."""
    assert HardwareReality.REAL_HARDWARE.value == "REAL_HARDWARE"
    assert HardwareReality.SIMULATION_VALIDATION.value == "SIMULATION_VALIDATION"
    assert TestVerdict.PASS.value == "PASS"
    assert TelemetryQuality.VALID.value == "VALID"
    assert TelemetryQuality.STALE.value == "STALE"
    assert FallbackReason.FALLBACK_CUDA_OOM.value == "FALLBACK_CUDA_OOM"

    acc = MemoryAccounting(
        total_dedicated_bytes=8 * 1024 * 1024 * 1024,
        total_shared_bytes=0,
        device_used_bytes=4 * 1024 * 1024 * 1024,
        device_free_bytes=4 * 1024 * 1024 * 1024,
        process_allocated_bytes=1024 * 1024 * 1024,
        process_reserved_bytes=1024 * 1024 * 1024,
        external_usage_estimate_bytes=3 * 1024 * 1024 * 1024,
    )
    assert acc.physical_usage_ratio == 0.5
    assert acc.usable_dedicated_vram == 7 * 1024 * 1024 * 1024
    assert round(acc.governance_usage_ratio, 2) == 0.57


def test_provenance_tracking() -> None:
    """Verify provenance container captures origin, confidence, and monotonic timestamp."""
    prov = ProvenanceValue(value="RTX 4090", source="NVML", confidence="HIGH")
    assert prov.value == "RTX 4090"
    assert prov.source == "NVML"
    assert prov.confidence == "HIGH"
    assert prov.captured_at_mono_ns > 0
    d = prov.to_dict()
    assert d["value"] == "RTX 4090"
    assert d["source"] == "NVML"


def test_permissions_inspector() -> None:
    """Verify Windows permission inspector returns valid profile."""
    profile = PermissionInspector.inspect()
    assert isinstance(profile.is_admin, bool)
    assert profile.wmi_access in ("AVAILABLE", "RESTRICTED", "UNAVAILABLE")
    assert profile.permission_tier in ("STANDARD_USER", "ELEVATED_ADMIN")


def test_layered_discovery() -> None:
    """Verify layered discovery enumerates compute devices including CPU baseline."""
    engine = LayeredDiscoveryEngine()
    devices = engine.discover_all()
    assert len(devices) >= 1
    # Check that baseline CPU is present
    has_cpu = any(d.device_type.value == DeviceType.CPU for d in devices)
    assert has_cpu
    cpu_dev = [d for d in devices if d.device_type.value == DeviceType.CPU][0]
    assert cpu_dev.backend_support == ["cpu"]


def test_telemetry_quality_and_freshness() -> None:
    """Verify 1000ms freshness invariant and sensor boundary checks."""
    validator = TelemetryQualityValidator(max_freshness_ms=1000)
    now_ns = time.monotonic_ns()

    # Valid temperature
    q_valid, _ = validator.validate_temperature(65.0, now_ns, now_ns + 100_000_000)
    assert q_valid == TelemetryQuality.VALID

    # Stale temperature (1500ms old)
    q_stale, _ = validator.validate_temperature(65.0, now_ns, now_ns + 1_500_000_000)
    assert q_stale == TelemetryQuality.STALE

    # Missing sensor reading
    q_missing, _ = validator.validate_temperature(None, now_ns, now_ns)
    assert q_missing == TelemetryQuality.MISSING

    # Out of range reading (160C)
    q_oor, _ = validator.validate_temperature(160.0, now_ns, now_ns)
    assert q_oor == TelemetryQuality.OUT_OF_RANGE


def test_telemetry_collector() -> None:
    """Verify telemetry collector stores time-series samples."""
    collector = TelemetryCollector()
    acc = MemoryAccounting(8000, 0, 4000, 4000, 1000, 1000, 3000)
    sample = collector.record_sample(
        device_index=0,
        temperature_c=55.0,
        memory=acc,
        gpu_utilization_pct=30.0,
    )
    assert sample.sample_id == 1
    assert sample.temperature_quality == TelemetryQuality.VALID
    assert len(collector.samples) == 1


def test_backend_adapters() -> None:
    """Verify CPU, CUDA, and DirectML adapter behavior."""
    cpu = CpuBackendAdapter()
    assert cpu.is_available()
    assert cpu.backend_name == "CPU"
    assert cpu.execute_dummy_workload()

    tensor = cpu.allocate_tensor(0, 1024)
    assert tensor is not None
    cpu.free_tensor(tensor)

    cuda = CudaBackendAdapter()
    assert cuda.backend_name == "CUDA"

    dml = DirectMLBackendAdapter()
    assert dml.backend_name == "DIRECTML"
    # probe capability stage should not throw
    stage = dml.probe_capability_stage()
    assert stage is not None


def test_memory_probe_and_voice_headroom() -> None:
    """Verify active voice headroom reservation probe defends against pressure."""
    cpu = CpuBackendAdapter()
    prober = ActiveVoiceHeadroomProber(cpu)
    res = prober.probe_voice_headroom(0, required_headroom_bytes=64 * 1024 * 1024)
    assert res["probe_success"]
    assert res["clean_recovery"]

    probe_engine = MemoryProbeEngine(cpu)
    cycles = probe_engine.run_allocation_cycle(0, [1024, 2048, 4096])
    assert cycles["chunks_completed"] == 3


def test_governance_reference_oracle() -> None:
    """Verify independent governance reference oracle calculates correct transitions."""
    oracle = GovernanceReferenceModel()

    # VRAM thresholds
    st_norm, act_norm = oracle.evaluate_vram_reference(0.50, 2_000_000_000, 4_000_000_000)
    assert (st_norm, act_norm) == ("NORMAL", "PROCEED")

    st_soft, act_soft = oracle.evaluate_vram_reference(0.76, 1_000_000_000, 4_000_000_000)
    assert (st_soft, act_soft) == ("SOFT_EXCEEDED", "TRIGGER_GC")

    st_hard, act_hard = oracle.evaluate_vram_reference(0.86, 1_000_000_000, 4_000_000_000)
    assert (st_hard, act_hard) == ("HARD_EXCEEDED", "PAUSE_EVALUATION")

    st_emerg, act_emerg = oracle.evaluate_vram_reference(0.93, 500_000_000, 4_000_000_000)
    assert (st_emerg, act_emerg) == ("EMERGENCY_EXCEEDED", "EMERGENCY_SUSPEND")

    # Headroom deficit
    st_hr, act_hr = oracle.evaluate_vram_reference(0.60, 500_000_000, 4_000_000_000)  # Free < 1GB
    assert (st_hr, act_hr) == ("HARD_EXCEEDED", "PAUSE_EVALUATION")

    # Thermal thresholds
    st_t_norm, act_t_norm = oracle.evaluate_thermal_reference(70.0, 0.0)
    assert (st_t_norm, act_t_norm) == ("NORMAL", "PROCEED")

    st_t_warn, act_t_warn = oracle.evaluate_thermal_reference(83.0, 5.0)
    assert (st_t_warn, act_t_warn) == ("WARNING", "PROCEED")

    st_t_thrott, act_t_thrott = oracle.evaluate_thermal_reference(83.0, 16.0)
    assert (st_t_thrott, act_t_thrott) == ("THROTTLED", "PAUSE_WORKERS")

    st_t_emerg, act_t_emerg = oracle.evaluate_thermal_reference(96.0, 0.0)
    assert (st_t_emerg, act_t_emerg) == ("EMERGENCY", "EMERGENCY_STOP")


def test_thermal_replay_hysteresis() -> None:
    """Verify deterministic thermal replay validates 82C pause and 75C resume."""
    replay = ThermalReplayEngine()
    rep = replay.run_standard_hysteresis_profile()
    assert rep.passed
    assert rep.pause_triggered
    assert rep.resume_triggered
    assert rep.evidence_level == EvidenceLevel.L2_IN_PROCESS_INTEGRATION
    assert rep.hardware_reality == HardwareReality.SIMULATION_VALIDATION

    emerg_rep = replay.run_emergency_stop_injection()
    assert emerg_rep.emergency_triggered
    assert emerg_rep.passed


def test_gpu_fault_injector() -> None:
    """Verify GPU fault injection matrix for OOM, sensor loss, and contention."""
    injector = GPUFaultInjector()
    oom = injector.test_cuda_oom_handling()
    assert oom.verdict == TestVerdict.PASS
    assert oom.fallback_reason == FallbackReason.FALLBACK_CUDA_OOM

    loss = injector.test_nvml_sensor_loss_handling()
    assert loss.verdict == TestVerdict.PASS
    assert loss.fallback_reason == FallbackReason.FALLBACK_GPU_TELEMETRY_UNSAFE

    contention = injector.test_external_process_contention()
    assert contention.verdict == TestVerdict.PASS


def test_single_instance_run_lock(tmp_path: pathlib.Path) -> None:
    """Verify run lock prevents duplicate execution and cleans up cleanly."""
    lock_file = tmp_path / "test_gpu_lab.lock"
    lock1 = SingleInstanceRunLock(lock_path=lock_file, session_id="s1")
    lock1.acquire()

    # Second lock acquisition while active should raise conflict
    lock2 = SingleInstanceRunLock(lock_path=lock_file, session_id="s2")
    with pytest.raises(LabRunConflictError):
        lock2.acquire()

    lock1.release()
    assert not lock_file.exists()


def test_recovery_validator() -> None:
    """Verify recovery validator captures baseline and audits memory recovery."""
    cpu = CpuBackendAdapter()
    validator = RecoveryValidator(cpu, 0)
    baseline = validator.capture_baseline()
    assert baseline.device_healthy

    validator.update_peak(current_temp=50.0, current_free_bytes=baseline.memory.device_free_bytes)
    audit = validator.evaluate_recovery()
    assert audit.recovery_status == "RESTORED"
    assert audit.memory_recovered


def test_event_hash_chain() -> None:
    """Verify event hash chain sequentially seals events and catches tampering."""
    chain = EventHashChain()
    e1 = chain.append_event("TEST_START", {"name": "test1"})
    e2 = chain.append_event("ALLOCATE", {"bytes": 1024})
    assert e2.previous_event_hash == e1.event_hash
    assert chain.verify_integrity()

    # Tampering test: simulate modifying an event payload in history
    object.__setattr__(chain._events[0], "event_hash", "bad_hash_value")
    assert not chain.verify_integrity()


def test_evidence_integrity_and_strict_l5_gate() -> None:
    """Verify SHA-256 digest, HMAC-SHA256 signature, and strict 10-point L5 gate."""
    test_dict = {"track": "2.1", "run_id": "test_123", "data": [1, 2, 3]}
    digest = EvidenceIntegritySealer.compute_sha256_digest(test_dict)
    assert len(digest) == 64

    secret = b"my_secret_key"
    attestation = EvidenceIntegritySealer.sign_attestation(digest, secret, "TEST_OPERATOR")
    test_dict["attestation"] = attestation
    assert EvidenceIntegritySealer.verify_attestation(test_dict, secret)

    # Strict L5 qualification gate: all 10 must be True
    full_pass_checklist = L5QualificationChecklist(
        physical_device_detected=True,
        actual_driver_queried=True,
        actual_workload_executed=True,
        actual_telemetry_observed=True,
        zero_mocks_used=True,
        raw_samples_retained=True,
        monotonic_timing_captured=True,
        environment_fingerprint_captured=True,
        recovery_snapshot_recorded=True,
        reproducible=True,
    )
    assert full_pass_checklist.is_l5_qualified
    assert full_pass_checklist.determine_effective_level() == EvidenceLevel.L5_REAL_HARDWARE

    # If any single item fails (e.g. zero_mocks_used = False), L5 is DENIED
    simulated_checklist = L5QualificationChecklist(
        physical_device_detected=True,
        actual_driver_queried=True,
        actual_workload_executed=True,
        actual_telemetry_observed=True,
        zero_mocks_used=False,  # MOCK/SIMULATION USED
        raw_samples_retained=True,
        monotonic_timing_captured=True,
        environment_fingerprint_captured=True,
        recovery_snapshot_recorded=True,
        reproducible=True,
    )
    assert not simulated_checklist.is_l5_qualified
    assert simulated_checklist.determine_effective_level() != EvidenceLevel.L5_REAL_HARDWARE


def test_gpu_lab_harness_end_to_end(tmp_path: pathlib.Path) -> None:
    """Verify full end-to-end laboratory run and report generation."""
    out_file = tmp_path / "gpu_lab_report.json"
    config = GPULabConfig(
        mode="full-lab",
        backend="cpu",
        duration_seconds=1.0,
        output_path=out_file,
    )
    harness = GPULabHarness(config)
    report = harness.run()

    assert report.schema_version == "1.0"
    assert report.track == "2.1"
    assert len(report.devices) >= 1
    assert len(report.test_records) >= 5
    assert report.recovery_report["recovery_status"] in ("RESTORED", "DEGRADED")
    assert report.attestation.get("integrity_digest")
    assert out_file.exists()
