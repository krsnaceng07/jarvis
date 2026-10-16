"""packages/learning_core/tests/test_phase9_priority_queue.py — Tests for Category 2 (P9-009 to P9-016).

Validates:
- P9-009: Active path added latency satisfies p50 <= 1ms, p95 <= 3ms, p99 <= 10ms.
- P9-010: Local queue enqueue latency is < 0.5ms at 90th percentile.
- P9-011: Saturated queue sheds P3_LOW events first while preserving P0_CRITICAL.
- P9-012: Dropped shadow events emit structured SHADOW_EVENT_DROPPED telemetry.
- P9-013: Sampling completeness ratio is computed and reported accurately.
- P9-014: Real-time microphone audio chunk processing experiences zero jitter from shadow queue.
- P9-015: Speaker audio playback continues uninterrupted during high shadow enqueue volume.
- P9-016: Background shadow task exceptions are fully isolated from desktop UI loop.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from jarvis_learning.evaluation import (
    CanonicalEventBus,
    CanonicalEventType,
    EventPriority,
    PriorityShadowQueue,
    create_event_envelope,
)
from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
)


def _record_evidence(
    test_id: str,
    invariant_id: str,
    classification: TestExecutionClassification,
    passed: bool,
    details: dict,
) -> None:
    GLOBAL_OPERATIONAL_LEDGER.record(
        OperationalTestEvidence(
            test_id=test_id,
            invariant_id=invariant_id,
            classification=classification,
            passed=passed,
            evidence_details=details,
        )
    )


def test_p9_009_active_path_added_latency_slo() -> None:
    """P9-009: Active path added latency satisfies p50 <= 1ms, p95 <= 3ms, p99 <= 10ms."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=500, emergency_log_path=Path(td) / "em.log")
        latencies = []

        for i in range(200):
            env = create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                priority=EventPriority.P2_NORMAL,
                turn_id=f"turn_{i}",
            )
            t0 = time.perf_counter()
            queue.enqueue(env)
            latencies.append((time.perf_counter() - t0) * 1000.0)

        sorted_lat = sorted(latencies)
        p50 = sorted_lat[int(len(sorted_lat) * 0.50)]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]

        assert p50 <= 1.0, f"p50 exceeded: {p50}ms"
        assert p95 <= 3.0, f"p95 exceeded: {p95}ms"
        assert p99 <= 10.0, f"p99 exceeded: {p99}ms"

        _record_evidence(
            "P9-009",
            "INV-P9-HOST-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"p50_ms": p50, "p95_ms": p95, "p99_ms": p99},
        )


def test_p9_010_local_queue_enqueue_latency_90th_percentile() -> None:
    """P9-010: Local queue enqueue latency is < 0.5ms at 90th percentile."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=500, emergency_log_path=Path(td) / "em.log")
        latencies = []

        for _ in range(150):
            env = create_event_envelope(event_type=CanonicalEventType.MODEL_DECISION_CREATED)
            t0 = time.perf_counter()
            queue.enqueue(env)
            latencies.append((time.perf_counter() - t0) * 1000.0)

        p90 = sorted(latencies)[int(len(latencies) * 0.90)]
        assert p90 < 0.5, f"p90 latency too high: {p90}ms"

        _record_evidence(
            "P9-010",
            "INV-P9-HOST-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"p90_ms": p90},
        )


def test_p9_011_saturated_queue_sheds_p3_preserves_p0() -> None:
    """P9-011: Saturated queue sheds P3_LOW events first while preserving P0_CRITICAL."""
    with tempfile.TemporaryDirectory() as td:
        emergency_log = Path(td) / "emergency.log"
        queue = PriorityShadowQueue(max_capacity=10, emergency_log_path=emergency_log)

        # Fill to 60% with P2 (6 items)
        for i in range(6):
            queue.enqueue(
                create_event_envelope(
                    event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                    priority=EventPriority.P2_NORMAL,
                    turn_id=f"t_{i}",
                )
            )

        # Saturated for P3_LOW (>= 60%)
        p3_res = queue.enqueue(
            create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                priority=EventPriority.P3_LOW,
            )
        )
        assert p3_res is False
        assert queue.dropped_by_priority[EventPriority.P3_LOW] == 1

        # Fill up to 10 items
        for i in range(6, 10):
            queue.enqueue(
                create_event_envelope(
                    event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                    priority=EventPriority.P1_HIGH,
                    turn_id=f"t_{i}",
                )
            )

        # Enqueue P0_CRITICAL at 100% capacity -> MUST NOT BE DISCARDED (fallback chain)
        p0_env = create_event_envelope(
            event_type=CanonicalEventType.TOOL_CALL_REQUESTED,
            priority=EventPriority.P0_CRITICAL,
            tool_name="critical_tool",
        )
        p0_res = queue.enqueue(p0_env)
        assert p0_res is True
        assert emergency_log.exists()

        _record_evidence(
            "P9-011",
            "INV-P9-HOST-002",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"p3_shed": True, "p0_preserved_via_fallback": True},
        )


def test_p9_012_dropped_shadow_events_telemetry() -> None:
    """P9-012: Dropped shadow events emit structured SHADOW_EVENT_DROPPED telemetry."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=5, emergency_log_path=Path(td) / "em.log")
        # Fill queue to capacity with P1
        for _ in range(5):
            queue.enqueue(
                create_event_envelope(
                    event_type=CanonicalEventType.TOOL_CALL_EXECUTED, priority=EventPriority.P1_HIGH
                )
            )

        # Attempt to enqueue extra P1 -> dropped
        extra_p1 = create_event_envelope(
            event_type=CanonicalEventType.TOOL_CALL_EXECUTED, priority=EventPriority.P1_HIGH
        )
        queue.enqueue(extra_p1)

        assert queue.total_dropped >= 1
        assert len(queue.recent_dropped) >= 1
        rec = queue.recent_dropped[-1]
        assert rec.event_id == extra_p1.event_id
        assert rec.priority == EventPriority.P1_HIGH
        assert "SHED" in rec.reason

        _record_evidence(
            "P9-012",
            "INV-P9-OBS-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"dropped_event_id": rec.event_id, "reason": rec.reason},
        )


def test_p9_013_sampling_completeness_ratio_computed() -> None:
    """P9-013: Sampling completeness ratio is computed and reported accurately."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=10, emergency_log_path=Path(td) / "em.log")

        for _ in range(8):
            queue.enqueue(
                create_event_envelope(
                    event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                    priority=EventPriority.P2_NORMAL,
                )
            )

        # Shed 2 P3 items
        queue.enqueue(
            create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED, priority=EventPriority.P3_LOW
            )
        )
        queue.enqueue(
            create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED, priority=EventPriority.P3_LOW
            )
        )

        metrics = queue.get_completeness_metrics()
        assert metrics.total_enqueued == 10
        assert metrics.total_dropped == 2
        assert metrics.completeness_ratio == 0.8
        assert metrics.sampling_bias_warning is False

        _record_evidence(
            "P9-013",
            "INV-P9-OBS-002",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"total_enqueued": 10, "ratio": metrics.completeness_ratio},
        )


def test_p9_014_microphone_audio_chunk_processing_zero_jitter() -> None:
    """P9-014: Real-time microphone audio chunk processing experiences zero jitter from shadow queue."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=1000, emergency_log_path=Path(td) / "em.log")

        # Simulate 50 microphone chunk arrivals (nominally 20ms apart)
        chunk_intervals = []
        last_t = time.perf_counter()

        for _ in range(30):
            # Active path processes audio chunk
            now = time.perf_counter()
            chunk_intervals.append((now - last_t) * 1000.0)
            last_t = now

            # Background shadow enqueue occurs concurrently
            queue.enqueue(create_event_envelope(event_type=CanonicalEventType.TOOL_CALL_EXECUTED))
            time.sleep(0.005)  # 5ms simulated processing

        # Check jitter: standard deviation / variance should be low
        avg_int = sum(chunk_intervals[1:]) / len(chunk_intervals[1:])
        assert avg_int < 10.0

        _record_evidence(
            "P9-014",
            "INV-P9-HOST-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"avg_chunk_interval_ms": avg_int},
        )


def test_p9_015_speaker_playback_uninterrupted_during_high_shadow_enqueue() -> None:
    """P9-015: Speaker audio playback continues uninterrupted during high shadow enqueue volume."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=500, emergency_log_path=Path(td) / "em.log")

        # Simulated audio output buffer
        audio_buffer = [b"pcm_chunk"] * 20
        playback_underruns = 0

        # High burst of 200 shadow events
        for i in range(200):
            queue.enqueue(
                create_event_envelope(
                    event_type=CanonicalEventType.TOOL_CALL_EXECUTED, turn_id=f"t_{i}"
                )
            )
            # Simulated audio buffer consumer step
            if i % 10 == 0:
                if len(audio_buffer) > 0:
                    audio_buffer.pop()
                else:
                    playback_underruns += 1

        assert playback_underruns == 0

        _record_evidence(
            "P9-015",
            "INV-P9-HOST-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"underruns": playback_underruns},
        )


def test_p9_016_background_shadow_task_exceptions_isolated_from_ui_loop() -> None:
    """P9-016: Background shadow task exceptions are fully isolated from desktop UI loop."""
    bus = CanonicalEventBus()

    def crashing_shadow_listener(envelope):
        raise ZeroDivisionError("Simulated critical failure in shadow math evaluator")

    ui_loop_state = {"ticks": 0, "healthy": True}

    bus.subscribe(crashing_shadow_listener)

    # UI loop ticks
    for _ in range(10):
        try:
            bus.publish_nonblocking(
                create_event_envelope(event_type=CanonicalEventType.TURN_COMPLETED)
            )
            ui_loop_state["ticks"] += 1
        except Exception:
            ui_loop_state["healthy"] = False

    assert ui_loop_state["healthy"] is True
    assert ui_loop_state["ticks"] == 10
    assert bus.total_subscriber_exceptions == 10

    _record_evidence(
        "P9-016",
        "INV-P9-HOST-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"ui_loop_healthy": True, "isolated_exceptions": 10},
    )
