"""Stage 10.2: Real Hardware and Resource Governance Scenarios.

Scenarios P10-007 to P10-014:
- P10-007: Device probe returns capability-specific states and accurate evidence levels (INV-P10-HW-001).
- P10-008: 3-tier VRAM thresholds enforce soft limit GC and hard limit pause (INV-P10-HW-002).
- P10-009: VRAM emergency ceiling (92%) triggers immediate worker suspension.
- P10-010: Thermal throttling pause (>=82C) and hysteresis resume (<=75C) with sustained duration (INV-P10-HW-003).
- P10-011: Sensor unavailable fails conservative and pauses workers.
- P10-012: Priority lease allocation protects P0 voice runtime headroom against P4 learning jobs.
- P10-013: Resource preemption: active tool P1 preempts lower priority shadow lease P3.
- P10-014: Expired lease release and reclamation.
"""

from __future__ import annotations


from jarvis_learning.hardware.device_probe import DeviceProbeEngine
from jarvis_learning.hardware.resource_lease import (
    LeasePriority,
    ResourceLeaseManager,
)
from jarvis_learning.hardware.thermal_monitor import (
    ThermalAction,
    ThermalMonitor,
    ThermalState,
    ThermalThresholds,
)
from jarvis_learning.hardware.vram_governor import (
    VRAMAction,
    VRAMGovernor,
    VRAMMetrics,
    VRAMState,
    VRAMThresholds,
)
from jarvis_learning.invariants_p10 import (
    EvidenceLevel,
    get_p10_evidence_ledger,
)


def test_p10_007_device_probe_capability_specific_states() -> None:
    """P10-007: Device probe returns capability-specific states and accurate evidence levels (INV-P10-HW-001)."""
    ledger = get_p10_evidence_ledger()

    engine = DeviceProbeEngine()
    devices = engine.probe_all_devices()

    assert len(devices) >= 1  # CPU baseline always present
    cpu_dev = next(d for d in devices if d.backend == "CPU")
    assert cpu_dev.evidence_level == EvidenceLevel.L2_IN_PROCESS_INTEGRATION
    assert cpu_dev.matrix.compute_runtime_available is True

    ledger.record(
        scenario_id="P10-007",
        invariant_id="INV-P10-HW-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"device_count": len(devices)},
    )


def test_p10_008_vram_soft_and_hard_thresholds() -> None:
    """P10-008: 3-tier VRAM thresholds enforce soft limit GC and hard limit pause (INV-P10-HW-002)."""
    ledger = get_p10_evidence_ledger()

    governor = VRAMGovernor(
        thresholds=VRAMThresholds(
            soft_limit_pct=0.75,
            hard_limit_pct=0.85,
            emergency_limit_pct=0.92,
            reserved_runtime_bytes=1024 * 1024 * 1024,
        )
    )

    total = 10 * 1024 * 1024 * 1024  # 10 GB

    # 1. Normal usage (50%)
    m_normal = VRAMMetrics(
        total_bytes=total,
        allocated_bytes=int(total * 0.50),
        reserved_bytes=int(total * 0.50),
        free_bytes=int(total * 0.50),
        peak_bytes=int(total * 0.50),
    )
    state, action = governor.evaluate(m_normal)
    assert state == VRAMState.NORMAL
    assert action == VRAMAction.PROCEED

    # 2. Soft limit exceeded (78%)
    m_soft = VRAMMetrics(
        total_bytes=total,
        allocated_bytes=int(total * 0.78),
        reserved_bytes=int(total * 0.78),
        free_bytes=int(total * 0.22),
        peak_bytes=int(total * 0.78),
    )
    state, action = governor.evaluate(m_soft)
    assert state == VRAMState.SOFT_EXCEEDED
    assert action == VRAMAction.TRIGGER_GC

    # 3. Hard limit exceeded (88%)
    m_hard = VRAMMetrics(
        total_bytes=total,
        allocated_bytes=int(total * 0.88),
        reserved_bytes=int(total * 0.88),
        free_bytes=int(total * 0.12),
        peak_bytes=int(total * 0.88),
    )
    state, action = governor.evaluate(m_hard)
    assert state == VRAMState.HARD_EXCEEDED
    assert action == VRAMAction.PAUSE_EVALUATION

    ledger.record(
        scenario_id="P10-008",
        invariant_id="INV-P10-HW-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={
            "soft_action": VRAMAction.TRIGGER_GC.value,
            "hard_action": VRAMAction.PAUSE_EVALUATION.value,
        },
    )


def test_p10_009_vram_emergency_suspension() -> None:
    """P10-009: VRAM emergency ceiling (92%) triggers immediate worker suspension."""
    ledger = get_p10_evidence_ledger()

    governor = VRAMGovernor()
    total = 8 * 1024 * 1024 * 1024  # 8 GB

    # Emergency spike (95%)
    m_emerg = VRAMMetrics(
        total_bytes=total,
        allocated_bytes=int(total * 0.95),
        reserved_bytes=int(total * 0.95),
        free_bytes=int(total * 0.05),
        peak_bytes=int(total * 0.95),
    )
    state, action = governor.evaluate(m_emerg)
    assert state == VRAMState.EMERGENCY_EXCEEDED
    assert action == VRAMAction.EMERGENCY_SUSPEND

    ledger.record(
        scenario_id="P10-009",
        invariant_id="INV-P10-HW-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"state": state.value, "action": action.value},
    )


def test_p10_010_thermal_hysteresis_and_sustained_duration() -> None:
    """P10-010: Thermal throttling pause (>=82C) and hysteresis resume (<=75C) with sustained duration (INV-P10-HW-003)."""
    ledger = get_p10_evidence_ledger()

    thresholds = ThermalThresholds(
        gpu_pause_c=82.0,
        gpu_resume_c=75.0,
        cpu_pause_c=85.0,
        cpu_resume_c=78.0,
        sustained_pause_sec=10.0,
        sustained_resume_sec=20.0,
    )
    monitor = ThermalMonitor(thresholds)

    t0 = 1000.0
    # 1. Normal temp (70C)
    state, action = monitor.update(gpu_temp_c=70.0, cpu_temp_c=65.0, current_time=t0)
    assert state == ThermalState.NORMAL
    assert action == ThermalAction.PROCEED

    # 2. Temp spikes to 83C at t0+1.0s (Warning, not yet throttled because < sustained_pause_sec)
    state, action = monitor.update(gpu_temp_c=83.0, cpu_temp_c=65.0, current_time=t0 + 1.0)
    assert state == ThermalState.WARNING
    assert action == ThermalAction.PROCEED

    # 3. Temp remains at 83C at t0+11.0s (>= 10.0s sustained -> THROTTLED)
    state, action = monitor.update(gpu_temp_c=83.0, cpu_temp_c=65.0, current_time=t0 + 11.0)
    assert state == ThermalState.THROTTLED
    assert action == ThermalAction.PAUSE_WORKERS

    # 4. Temp drops to 74C at t0+15.0s (below resume, but not yet sustained for 20.0s -> remains THROTTLED)
    state, action = monitor.update(gpu_temp_c=74.0, cpu_temp_c=65.0, current_time=t0 + 15.0)
    assert state == ThermalState.THROTTLED
    assert action == ThermalAction.PAUSE_WORKERS

    # 5. Temp stays at 74C at t0+36.0s (sustained >= 20.0s -> recovered to NORMAL)
    state, action = monitor.update(gpu_temp_c=74.0, cpu_temp_c=65.0, current_time=t0 + 36.0)
    assert state == ThermalState.NORMAL
    assert action == ThermalAction.PROCEED

    ledger.record(
        scenario_id="P10-010",
        invariant_id="INV-P10-HW-003",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"final_state": state.value},
    )


def test_p10_011_sensor_unavailable_fails_conservative() -> None:
    """P10-011: Missing sensor telemetry triggers SENSOR_UNAVAILABLE and pauses workers."""
    ledger = get_p10_evidence_ledger()

    monitor = ThermalMonitor()
    state, action = monitor.update(gpu_temp_c=None, cpu_temp_c=None)

    assert state == ThermalState.SENSOR_UNAVAILABLE
    assert action == ThermalAction.PAUSE_WORKERS

    ledger.record(
        scenario_id="P10-011",
        invariant_id="INV-P10-HW-003",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"state": state.value, "action": action.value},
    )


def test_p10_012_priority_lease_protects_p0_voice_runtime() -> None:
    """P10-012: Priority lease allocation protects P0 voice runtime headroom against P4 learning jobs."""
    ledger = get_p10_evidence_ledger()

    manager = ResourceLeaseManager()
    total_capacity = 1000

    # 1. P0 Voice acquires 400
    voice_lease = manager.acquire_lease(
        resource_type="MEMORY_MB",
        device_id="sys_mem",
        owner="voice_assistant",
        priority=LeasePriority.P0_VOICE_AUDIO,
        amount=400,
        total_capacity=total_capacity,
    )
    assert voice_lease is not None
    assert voice_lease.preemptible is False

    # 2. P4 Shadow learning requests 700 (400 + 700 > 1000, and cannot preempt P0)
    p4_lease = manager.acquire_lease(
        resource_type="MEMORY_MB",
        device_id="sys_mem",
        owner="shadow_trainer",
        priority=LeasePriority.P4_TRAINING_SHADOW,
        amount=700,
        total_capacity=total_capacity,
    )
    assert p4_lease is None  # Blocked to protect P0

    ledger.record(
        scenario_id="P10-012",
        invariant_id="INV-P10-HW-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"p0_granted": True, "p4_blocked": True},
    )


def test_p10_013_active_tool_preempts_shadow_lease() -> None:
    """P10-013: Active user tool (P1) preempts lower priority shadow lease (P3)."""
    ledger = get_p10_evidence_ledger()

    manager = ResourceLeaseManager()
    total_capacity = 1000

    # 1. P3 Shadow evaluation acquires 600
    p3_lease = manager.acquire_lease(
        resource_type="GPU_COMPUTE",
        device_id="gpu_0",
        owner="eval_worker",
        priority=LeasePriority.P3_EVALUATION,
        amount=600,
        total_capacity=total_capacity,
    )
    assert p3_lease is not None
    assert p3_lease.is_active is True
    assert p3_lease.preemptible is True

    # 2. P1 Active tool needs 800 (available is only 400, so P3 must be preempted)
    p1_lease = manager.acquire_lease(
        resource_type="GPU_COMPUTE",
        device_id="gpu_0",
        owner="browser_tool",
        priority=LeasePriority.P1_ACTIVE_TOOL,
        amount=800,
        total_capacity=total_capacity,
    )
    assert p1_lease is not None
    assert p1_lease.is_active is True
    assert p3_lease.is_active is False  # Preempted

    ledger.record(
        scenario_id="P10-013",
        invariant_id="INV-P10-HW-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"p3_preempted": True, "p1_granted": True},
    )


def test_p10_014_expired_lease_reclamation() -> None:
    """P10-014: Expired leases are cleaned and capacity is reclaimed."""
    ledger = get_p10_evidence_ledger()

    manager = ResourceLeaseManager()
    t0 = 2000.0

    lease = manager.acquire_lease(
        resource_type="CPU_SLOT",
        device_id="cpu_0",
        owner="temp_job",
        priority=LeasePriority.P3_EVALUATION,
        amount=500,
        total_capacity=500,
        ttl_sec=10.0,
        current_time=t0,
    )
    assert lease is not None
    assert len(manager.get_active_leases()) == 1

    # At t0+5s -> still active
    cleaned = manager.clean_expired(current_time=t0 + 5.0)
    assert cleaned == 0
    assert len(manager.get_active_leases()) == 1

    # At t0+12s -> expired
    cleaned = manager.clean_expired(current_time=t0 + 12.0)
    assert cleaned == 1
    assert len(manager.get_active_leases()) == 0

    ledger.record(
        scenario_id="P10-014",
        invariant_id="INV-P10-HW-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"reclaimed": cleaned},
    )
