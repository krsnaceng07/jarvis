"""Stage 10.5: Real JARVIS Runtime Integration & User Workflows Scenarios.

Scenarios P10-031 to P10-038:
- P10-031: Active voice hook latency SLO verified (p99 <= 2.0ms) under load.
- P10-032: Unidirectional dependency: worker or queue stall never blocks active path (INV-P10-RT-001).
- P10-033: Workflow A: YouTube browser tab reuse and continuity.
- P10-034: Workflow B: Honest tool failure attribution without false success (INV-P10-RT-003).
- P10-035: Workflow C: Voice barge-in interruption cancels TTS and discards stale sidecar.
- P10-036: Workflow D: Worker crash during voice turn causes zero audio underrun or delay.
- P10-037: Workflow E: Task generation advancement rejects stale worker outputs (INV-P10-RT-002).
- P10-038: Ring buffer load shedding under burst events maintains active path isolation.
"""

from __future__ import annotations

from jarvis_learning.evaluation.event_envelope import (
    CanonicalEventType,
    EventPriority,
    create_event_envelope,
)
from jarvis_learning.invariants_p10 import (
    EvidenceLevel,
    get_p10_evidence_ledger,
)
from jarvis_learning.runtime.voice_guard import UnidirectionalVoiceGuard
from jarvis_learning.runtime.workflow_verifier import WorkflowVerifier


def test_p10_031_voice_hook_latency_slo_under_load() -> None:
    """P10-031: Active voice hook latency SLO verified (p99 <= 2.0ms) under burst load."""
    ledger = get_p10_evidence_ledger()

    guard = UnidirectionalVoiceGuard(capacity=500)

    # Emit 200 events from active voice loop
    for i in range(200):
        env = create_event_envelope(
            event_type=CanonicalEventType.USER_TURN_STARTED,
            priority=EventPriority.P0_CRITICAL,
            session_id="session_voice",
            turn_id=f"turn_{i // 10}",
            sanitized_arguments={"chunk_index": i},
        )
        guard.emit_event_from_active_path(env)

    slo = guard.get_slo_metrics()
    assert slo.sample_count == 200
    assert slo.p99_ms <= 2.0  # Must adhere to strict latency ceiling

    ledger.record(
        scenario_id="P10-031",
        invariant_id="INV-P10-RT-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"p50_ms": slo.p50_ms, "p99_ms": slo.p99_ms},
    )


def test_p10_032_unidirectional_dependency_zero_blocking() -> None:
    """P10-032: Unidirectional dependency: worker or queue stall never causes active path block (INV-P10-RT-001)."""
    ledger = get_p10_evidence_ledger()

    guard = UnidirectionalVoiceGuard(capacity=50)

    # Completely fill the buffer
    for i in range(100):
        env = create_event_envelope(
            event_type=CanonicalEventType.USER_TURN_STARTED,
            priority=EventPriority.P3_LOW,
            session_id="session_test",
            turn_id="turn_flood",
            sanitized_arguments={},
        )
        # Must return immediately without throwing or blocking
        ok = guard.emit_event_from_active_path(env)
        assert ok is True

    slo = guard.get_slo_metrics()
    assert slo.dropped_events_count == 50  # Shed excess without blocking

    ledger.record(
        scenario_id="P10-032",
        invariant_id="INV-P10-RT-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"dropped_count": slo.dropped_events_count},
    )


def test_p10_033_workflow_a_youtube_tab_reuse() -> None:
    """P10-033: Workflow A: YouTube browser tab reuse and continuity."""
    ledger = get_p10_evidence_ledger()

    verifier = WorkflowVerifier()
    res = verifier.run_workflow_a_youtube_tab_reuse()
    assert res.passed is True
    assert res.details["active_tab_count"] == 1

    ledger.record(
        scenario_id="P10-033",
        invariant_id="INV-P10-RT-003",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details=res.details,
    )


def test_p10_034_workflow_b_honest_failure_attribution() -> None:
    """P10-034: Workflow B: Honest tool failure attribution without false success (INV-P10-RT-003)."""
    ledger = get_p10_evidence_ledger()

    verifier = WorkflowVerifier()
    res = verifier.run_workflow_b_honest_failure_attribution(
        tool_name="system_automation",
        tool_error="DEVICE_NOT_FOUND",
    )
    assert res.passed is True
    assert res.details["false_success_detected"] is False

    ledger.record(
        scenario_id="P10-034",
        invariant_id="INV-P10-RT-003",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details=res.details,
    )


def test_p10_035_workflow_c_voice_barge_in_cancellation() -> None:
    """P10-035: Workflow C: Voice barge-in interruption cancels TTS and discards stale sidecar."""
    ledger = get_p10_evidence_ledger()

    verifier = WorkflowVerifier()
    res = verifier.run_workflow_c_voice_interruption()
    assert res.passed is True
    assert res.details["worker_result_accepted"] is False

    ledger.record(
        scenario_id="P10-035",
        invariant_id="INV-P10-RT-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details=res.details,
    )


def test_p10_036_workflow_d_worker_crash_voice_continuity() -> None:
    """P10-036: Workflow D: Worker crash during voice turn causes zero audio underrun or delay."""
    ledger = get_p10_evidence_ledger()

    verifier = WorkflowVerifier()
    res = verifier.run_workflow_d_worker_crash_containment()
    assert res.passed is True
    assert res.details["active_path_blocked"] is False

    ledger.record(
        scenario_id="P10-036",
        invariant_id="INV-P10-RT-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details=res.details,
    )


def test_p10_037_workflow_e_task_generation_continuity() -> None:
    """P10-037: Workflow E: Task generation advancement rejects stale worker outputs (INV-P10-RT-002)."""
    ledger = get_p10_evidence_ledger()

    verifier = WorkflowVerifier()
    res = verifier.run_workflow_e_task_generation_continuity()
    assert res.passed is True
    assert res.details["stale_rejected"] is True
    assert res.details["fresh_accepted"] is True

    ledger.record(
        scenario_id="P10-037",
        invariant_id="INV-P10-RT-002",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details=res.details,
    )


def test_p10_038_ring_buffer_load_shedding_preserves_isolation() -> None:
    """P10-038: Ring buffer load shedding under burst events maintains active path isolation."""
    ledger = get_p10_evidence_ledger()

    guard = UnidirectionalVoiceGuard(capacity=10)

    # Burst of 50 events
    for i in range(50):
        env = create_event_envelope(
            event_type=CanonicalEventType.USER_TURN_STARTED,
            priority=EventPriority.P3_LOW,
            session_id="burst_sess",
            turn_id=f"turn_{i}",
            sanitized_arguments={"i": i},
        )
        guard.emit_event_from_active_path(env)

    slo = guard.get_slo_metrics()
    assert slo.dropped_events_count == 40
    assert slo.p99_ms <= 2.0

    ledger.record(
        scenario_id="P10-038",
        invariant_id="INV-P10-RT-001",
        evidence_level=EvidenceLevel.L2_IN_PROCESS_INTEGRATION,
        passed=True,
        details={"dropped_count": slo.dropped_events_count},
    )
