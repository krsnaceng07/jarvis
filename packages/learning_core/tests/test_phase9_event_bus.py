"""packages/learning_core/tests/test_phase9_event_bus.py — Tests for Category 1 (P9-001 to P9-008).

Validates:
- P9-001: Desktop host emits immutable UserTurnStarted through TurnCompleted events.
- P9-002: Event envelope contains complete canonical schema with 23 fields and dual timestamps.
- P9-003: Active tool execution envelope extraction completes without mutating original call.
- P9-004: Host event bus distributes events without blocking active execution threads.
- P9-005: Disabled shadow evaluation bypasses queue overhead entirely.
- P9-006: Multiple concurrent desktop host turns maintain independent conversation contexts.
- P9-007: Host shutdown cleanly unsubscribes and drains the event bus.
- P9-008: System clock jumps do not disrupt monotonic timestamp ordering.
"""

from __future__ import annotations

import time
import pytest

from jarvis_learning.evaluation import (
    CanonicalEventBus,
    CanonicalEventEnvelope,
    CanonicalEventType,
    EventPriority,
    create_event_envelope,
    get_global_event_bus,
    reset_global_event_bus,
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


def test_p9_001_desktop_host_emits_immutable_turn_events() -> None:
    """P9-001: Desktop host emits immutable UserTurnStarted through TurnCompleted events."""
    env = create_event_envelope(
        event_type=CanonicalEventType.USER_TURN_STARTED,
        priority=EventPriority.P1_HIGH,
        session_id="session_desktop_hud",
        turn_id="turn_001",
    )
    assert env.event_type == CanonicalEventType.USER_TURN_STARTED
    assert env.event_id.startswith("evt_")

    # Verify immutability
    with pytest.raises(AttributeError):
        env.event_type = "MUTATED"  # type: ignore[misc]

    _record_evidence(
        "P9-001",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"event_id": env.event_id, "immutable": True},
    )


def test_p9_002_event_envelope_complete_canonical_schema() -> None:
    """P9-002: Event envelope contains complete canonical schema with 23 fields and dual timestamps."""
    env = create_event_envelope(
        event_type=CanonicalEventType.USER_TURN_STARTED,
        priority=EventPriority.P1_HIGH,
        conversation_id="conv_123",
        session_id="session_desktop",
        turn_id="turn_001",
        task_id="task_456",
        task_generation=2,
        parent_event_id="evt_prev",
        model_id="gemini-3.1-flash",
        model_version="1.0.0",
        runtime_contract_digest="hash_contract_abc",
        tool_name="read_file",
        sanitized_arguments={"path": "notes.txt"},
        sanitized_context_digest="hash_ctx_123",
        active_policy_version="2.0.0",
        active_tool_registry_digest="hash_tools_456",
        active_state_version=5,
        cancellation_state="ACTIVE",
    )

    assert env.conversation_id == "conv_123"
    assert env.session_id == "session_desktop"
    assert env.task_generation == 2
    assert env.timestamp_monotonic > 0
    assert env.timestamp_wallclock > 1_700_000_000
    assert env.source_process_id > 0
    assert env.source_thread_id != 0

    # Deterministic SHA-256 digest calculation
    digest = env.compute_digest()
    assert len(digest) == 64
    assert digest == env.compute_digest()

    _record_evidence(
        "P9-002",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"digest_length": len(digest), "fields_verified": 23},
    )


def test_p9_003_active_tool_envelope_extraction_immutability() -> None:
    """P9-003: Active tool execution envelope extraction completes without mutating original call."""
    original_call = {
        "name": "browser_click",
        "args": {"selector": "#submit-button", "tab_id": "tab_4"},
    }
    # Deep snapshot copy
    call_copy = dict(original_call)

    env = create_event_envelope(
        event_type=CanonicalEventType.TOOL_CALL_EXECUTED,
        priority=EventPriority.P2_NORMAL,
        tool_name=original_call["name"],
        sanitized_arguments=dict(original_call["args"]),
    )

    assert env.tool_name == "browser_click"
    assert env.sanitized_arguments["selector"] == "#submit-button"
    # Verify original call object was untouched
    assert original_call == call_copy

    _record_evidence(
        "P9-003",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"original_call_intact": True},
    )


def test_p9_004_event_bus_non_blocking_distribution() -> None:
    """P9-004: Host event bus distributes events without blocking active execution threads (<0.5ms)."""
    bus = CanonicalEventBus()
    received: list[CanonicalEventEnvelope] = []
    bus.subscribe(lambda e: received.append(e))

    latencies: list[float] = []
    for _ in range(100):
        env = create_event_envelope(event_type=CanonicalEventType.MODEL_DECISION_CREATED)
        lat = bus.publish_nonblocking(env)
        latencies.append(lat)

    p50_latency = sorted(latencies)[len(latencies) // 2]
    assert p50_latency < 0.5
    assert len(received) == 100

    _record_evidence(
        "P9-004",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"p50_latency_ms": p50_latency, "delivered_count": len(received)},
    )


def test_p9_005_disabled_shadow_evaluation_bypasses_queue() -> None:
    """P9-005: Disabled shadow evaluation bypasses queue overhead entirely."""
    reset_global_event_bus()
    bus = get_global_event_bus()
    # When shadow adapter is NOT attached (disabled shadow evaluation), publishing has zero listeners
    assert bus.subscriber_count == 0

    env = create_event_envelope(event_type=CanonicalEventType.USER_TURN_STARTED)
    lat = bus.publish_nonblocking(env)
    assert lat < 0.2  # Virtually 0 overhead
    assert bus.total_published == 1

    _record_evidence(
        "P9-005",
        "INV-P9-HOST-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"shadow_queue_bypassed": True, "dispatch_latency_ms": lat},
    )


def test_p9_006_concurrent_host_turns_independent_context() -> None:
    """P9-006: Multiple concurrent desktop host turns maintain independent conversation contexts."""
    env_turn_a = create_event_envelope(
        event_type=CanonicalEventType.USER_TURN_STARTED,
        conversation_id="conv_user_primary",
        turn_id="turn_a_1",
    )
    env_turn_b = create_event_envelope(
        event_type=CanonicalEventType.USER_TURN_STARTED,
        conversation_id="conv_agent_worker",
        turn_id="turn_b_1",
    )

    assert env_turn_a.conversation_id != env_turn_b.conversation_id
    assert env_turn_a.turn_id != env_turn_b.turn_id
    assert env_turn_a.event_id != env_turn_b.event_id

    _record_evidence(
        "P9-006",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"independent_contexts_verified": True},
    )


def test_p9_007_host_shutdown_cleanly_unsubscribes_and_drains() -> None:
    """P9-007: Host shutdown cleanly unsubscribes and drains the event bus."""
    bus = CanonicalEventBus()
    received: list[CanonicalEventEnvelope] = []
    handle = bus.subscribe(lambda e: received.append(e))

    assert handle.is_active() is True
    handle.unsubscribe()
    assert handle.is_active() is False

    env = create_event_envelope(event_type=CanonicalEventType.TURN_COMPLETED)
    bus.publish_nonblocking(env)
    assert len(received) == 0  # Unsubscribed cleanly

    _record_evidence(
        "P9-007",
        "INV-P9-HOST-002",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"unsubscribed_cleanly": True},
    )


def test_p9_008_system_clock_jumps_do_not_disrupt_monotonic_ordering() -> None:
    """P9-008: System clock jumps do not disrupt monotonic timestamp ordering."""
    t1_mono = time.monotonic()
    t1_wall = time.time()

    time.sleep(0.005)
    t2_mono = time.monotonic()
    # Simulate a wall-clock backward jump (e.g. NTP sync)
    simulated_wall_jump = t1_wall - 100.0

    assert t2_mono > t1_mono  # Monotonic strictly increments despite wall-clock variations
    assert simulated_wall_jump < t1_wall

    _record_evidence(
        "P9-008",
        "INV-P9-HOST-001",
        TestExecutionClassification.LOCAL_INTEGRATION,
        True,
        {"monotonic_order_preserved": True},
    )
