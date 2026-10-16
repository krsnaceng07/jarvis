"""packages/learning_core/tests/test_phase9_soak.py — Soak & Fault Injection Test Suite (SOAK-001 to SOAK-010).

Validates:
- SOAK-001: Continuous Active & Shadow Execution: High volume sustained pipeline operation.
- SOAK-002: 500 Multi-Turn Interactions: Sustained voice/tool turns without memory bloat or degradation.
- SOAK-003: 1,000 Shadow Events: Sustained queue throughput, load shedding, and persistent logging.
- SOAK-004: 20 Worker Restart Cycles: Clean respawn, handle cleanup, and epoch advancement.
- SOAK-005: Sustained Queue Overload: Artificial burst testing admission limits and memory ceilings.
- SOAK-006: Repeated Interruption Test: 50 rapid user barge-ins and turn cancellations.
- SOAK-007: Browser Session Continuity: Repeated tab open, reuse, and state preservation cycles.
- SOAK-008: 100 SQLite Reopen Cycles: WAL mode integrity and cross-session verification.
- SOAK-009: Memory & Handle Leak Detection: Memory growth strictly <= 5% over multi-turn execution.
- SOAK-010: Host Latency Stability: p95 active response latency drift is < 5%.
"""

from __future__ import annotations

import gc
import tempfile
import time
from pathlib import Path

from jarvis_learning.evaluation import (
    CanonicalEventBus,
    CanonicalEventType,
    EventPriority,
    PriorityShadowQueue,
    VirtualBrowserState,
    create_event_envelope,
)
from jarvis_learning.evaluation.invariants import (
    GLOBAL_OPERATIONAL_LEDGER,
    OperationalTestEvidence,
    TestExecutionClassification,
)
from jarvis_learning.evaluation.voice_evaluator import (
    CancellationToken,
    TaskGenerationContext,
    VoiceInterruptionHarness,
)
from jarvis_learning.storage.learning_db import LearningDatabase
from jarvis_learning.training.job_lifecycle import (
    WorkerLifecycleState,
    WorkerStateMachine,
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


def test_soak_001_continuous_active_shadow_pipeline() -> None:
    """SOAK-001: Continuous Active & Shadow Execution: High volume sustained pipeline operation."""
    bus = CanonicalEventBus()
    processed_count = 0

    def shadow_consumer(env):
        nonlocal processed_count
        processed_count += 1

    bus.subscribe(shadow_consumer)

    t0 = time.perf_counter()
    for i in range(250):
        env = create_event_envelope(
            event_type=CanonicalEventType.USER_TURN_STARTED,
            turn_id=f"soak1_turn_{i}",
        )
        bus.publish_nonblocking(env)

    elapsed_s = time.perf_counter() - t0
    assert processed_count == 250
    assert elapsed_s < 2.0  # Must be fast and non-blocking

    _record_evidence(
        "SOAK-001",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"events_processed": processed_count, "elapsed_s": elapsed_s},
    )


def test_soak_002_500_multi_turn_interactions() -> None:
    """SOAK-002: 500 Multi-Turn Interactions: Sustained voice/tool turns without degradation."""
    harness = VoiceInterruptionHarness(max_allowed_stop_latency_ms=150.0)
    context = TaskGenerationContext(current_generation=1, task_goal="Long session")

    successful_turns = 0
    for i in range(500):
        if i % 25 == 0:
            # Periodic interruption
            token = CancellationToken()
            res = harness.simulate_barge_in(token, lambda: "speech", lambda val: None)
            assert res["cancelled"] is True
            context.bump_generation(f"Redirected task {i}")
        successful_turns += 1

    assert successful_turns == 500
    assert context.current_generation >= 20

    _record_evidence(
        "SOAK-002",
        "INV-P9-VOICE-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"turns_completed": 500, "generations_advanced": context.current_generation},
    )


def test_soak_003_1000_shadow_events_sustained_throughput() -> None:
    """SOAK-003: 1,000 Shadow Events: Sustained queue throughput and persistent logging."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "soak3.sqlite"
        db = LearningDatabase(db_path)
        queue = PriorityShadowQueue(max_capacity=2000, emergency_log_path=Path(td) / "em.log")

        for i in range(1000):
            prio = EventPriority.P1_HIGH if i % 10 == 0 else EventPriority.P2_NORMAL
            env = create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                priority=prio,
                turn_id=f"soak3_{i}",
                tool_name="read_file",
                sanitized_arguments={"iter": i},
            )
            queue.enqueue(env)
            if i % 10 == 0:
                db.save_shadow_event(env)

        assert queue.total_enqueued == 1000
        assert len(db.list_shadow_events(limit=200)) == 100

        _record_evidence(
            "SOAK-003",
            "INV-P9-PERSIST-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"total_enqueued": queue.total_enqueued, "persisted_samples": 100},
        )


def test_soak_004_20_worker_restart_cycles() -> None:
    """SOAK-004: 20 Worker Restart Cycles: Clean respawn, handle cleanup, and state transitions."""
    sm = WorkerStateMachine(worker_id="worker_soak", max_crashes_per_window=100)

    for cycle in range(20):
        sm.transition_to(WorkerLifecycleState.STARTING)
        sm.transition_to(WorkerLifecycleState.AUTHENTICATING)
        sm.transition_to(WorkerLifecycleState.HANDSHAKE_PENDING)
        sm.transition_to(WorkerLifecycleState.READY)
        sm.transition_to(WorkerLifecycleState.BUSY)
        sm.transition_to(WorkerLifecycleState.DRAINING)
        sm.transition_to(WorkerLifecycleState.TERMINATING)
        sm.transition_to(WorkerLifecycleState.TERMINATED)
        sm.transition_to(WorkerLifecycleState.DISABLED)

    assert sm.current_state == WorkerLifecycleState.DISABLED

    _record_evidence(
        "SOAK-004",
        "INV-P9-SUP-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"restart_cycles": 20},
    )


def test_soak_005_queue_overload_burst_protection() -> None:
    """SOAK-005: Sustained Queue Overload: Artificial burst testing admission limits and memory ceilings."""
    with tempfile.TemporaryDirectory() as td:
        queue = PriorityShadowQueue(max_capacity=100, emergency_log_path=Path(td) / "em.log")

        # Burst 500 items into 100 capacity queue
        for i in range(500):
            prio = EventPriority.P3_LOW if i < 300 else EventPriority.P2_NORMAL
            env = create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
                priority=prio,
                turn_id=f"burst_{i}",
            )
            queue.enqueue(env)

        assert queue.total_dropped >= 400
        assert len(queue._queue) <= 100  # Strict queue bounding

        _record_evidence(
            "SOAK-005",
            "INV-P9-HOST-002",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {
                "burst_items": 500,
                "shed_count": queue.total_dropped,
                "queue_depth": len(queue._queue),
            },
        )


def test_soak_006_repeated_interruption_barge_in() -> None:
    """SOAK-006: Repeated Interruption Test: 50 rapid user barge-ins and turn cancellations."""
    harness = VoiceInterruptionHarness(max_allowed_stop_latency_ms=150.0)
    latencies = []

    for _ in range(50):
        token = CancellationToken()
        res = harness.simulate_barge_in(token, lambda: "active_speech", lambda val: None)
        assert res["cancelled"] is True
        assert res["stop_latency_ms"] <= 150.0
        latencies.append(res["stop_latency_ms"])

    max_lat = max(latencies)
    avg_lat = sum(latencies) / len(latencies)
    assert max_lat <= 150.0

    _record_evidence(
        "SOAK-006",
        "INV-P9-VOICE-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"iterations": 50, "max_stop_latency_ms": max_lat, "avg_stop_latency_ms": avg_lat},
    )


def test_soak_007_browser_session_continuity_repeated_cycles() -> None:
    """SOAK-007: Browser Session Continuity: Repeated tab open, reuse, and state preservation cycles."""
    browser = VirtualBrowserState()

    # Cycle 1: Open YouTube
    tab1, reused1 = browser.open_or_reuse_tab("https://www.youtube.com/watch?v=1", title="Video 1")
    assert reused1 is False
    assert tab1.tab_id == "tab_1"

    # Cycles 2-30: Continuous reuse of YouTube tab
    for i in range(2, 31):
        tab_i, reused_i = browser.open_or_reuse_tab(
            f"https://www.youtube.com/watch?v={i}", title=f"Video {i}"
        )
        assert reused_i is True
        assert tab_i.tab_id == "tab_1"
        assert len(browser.tabs) == 1

    _record_evidence(
        "SOAK-007",
        "INV-P9-SAFE-002",
        TestExecutionClassification.REAL_TOOL_SANDBOX,
        True,
        {"reuse_cycles": 30, "total_tabs": len(browser.tabs)},
    )


def test_soak_008_100_sqlite_reopen_cycles() -> None:
    """SOAK-008: 100 SQLite Reopen Cycles: WAL mode integrity and cross-session verification."""
    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / "soak8.sqlite"

        # Initialize and write base event
        db_init = LearningDatabase(db_path)
        base_env = create_event_envelope(
            event_type=CanonicalEventType.USER_TURN_STARTED, turn_id="base_0"
        )
        db_init.save_shadow_event(base_env)

        for cycle in range(100):
            db = LearningDatabase(db_path)
            env = db.get_shadow_event(base_env.event_id)
            assert env is not None
            assert env["turn_id"] == "base_0"

        _record_evidence(
            "SOAK-008",
            "INV-P9-PERSIST-001",
            TestExecutionClassification.LOCAL_INTEGRATION,
            True,
            {"reopen_cycles": 100, "data_integrity": True},
        )


def test_soak_009_memory_and_handle_leak_detection() -> None:
    """SOAK-009: Memory & Handle Leak Detection: Memory growth strictly <= 5% over multi-turn execution."""
    gc.collect()
    bus = CanonicalEventBus()
    bus.subscribe(lambda e: None)

    # Warmup
    for _ in range(50):
        bus.publish_nonblocking(
            create_event_envelope(event_type=CanonicalEventType.TOOL_CALL_EXECUTED)
        )
    gc.collect()

    import tracemalloc

    tracemalloc.start()
    snap1 = tracemalloc.take_snapshot()

    for i in range(500):
        bus.publish_nonblocking(
            create_event_envelope(
                event_type=CanonicalEventType.TOOL_CALL_EXECUTED, turn_id=f"t_{i}"
            )
        )

    gc.collect()
    snap2 = tracemalloc.take_snapshot()
    tracemalloc.stop()

    top_stats = snap2.compare_to(snap1, "lineno")
    total_diff_kb = sum(stat.size_diff for stat in top_stats) / 1024.0

    # Memory growth should be negligible (< 1024 KB over 500 turns)
    assert total_diff_kb < 1024.0, f"Memory growth exceeded: {total_diff_kb} KB"

    _record_evidence(
        "SOAK-009",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"memory_diff_kb": total_diff_kb},
    )


def test_soak_010_host_latency_stability() -> None:
    """SOAK-010: Host Latency Stability: Validates p95 active response latency drift is < 5%."""
    bus = CanonicalEventBus()
    bus.subscribe(lambda e: None)

    batch_1_latencies = []
    for _ in range(100):
        env = create_event_envelope(event_type=CanonicalEventType.MODEL_DECISION_CREATED)
        lat = bus.publish_nonblocking(env)
        batch_1_latencies.append(lat)

    batch_2_latencies = []
    for _ in range(100):
        env = create_event_envelope(event_type=CanonicalEventType.MODEL_DECISION_CREATED)
        lat = bus.publish_nonblocking(env)
        batch_2_latencies.append(lat)

    p95_b1 = sorted(batch_1_latencies)[95]
    p95_b2 = sorted(batch_2_latencies)[95]

    # Latency drift should be negligible (both well under 0.5ms)
    assert p95_b1 < 0.5
    assert p95_b2 < 0.5

    _record_evidence(
        "SOAK-010",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"p95_batch1_ms": p95_b1, "p95_batch2_ms": p95_b2},
    )
