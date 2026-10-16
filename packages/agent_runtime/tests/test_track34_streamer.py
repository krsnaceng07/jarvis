"""Test suite for Track 3.4 Event Streaming, Sequencing & Secret Redaction (Phase 3.4-G).

Validates:
1. Independent per-connection sequencing (Invariant T34-04).
2. Secret redaction from telemetry stream chunks (Invariant T34-22).
3. Authorization filtering before projection (Invariant T34-21).
4. Backpressure drop behavior: telemetry dropped under high-water mark, structural events preserved.
"""

from __future__ import annotations

from jarvis_agent.gateway.backpressure import BackpressureQueue
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.gateway.redactor import redact_sensitive_text
from jarvis_agent.gateway.session_registry import SessionRegistry
from jarvis_agent.gateway.streamer import StreamBroadcaster


def test_sensitive_text_redaction() -> None:
    text = "Connecting with Bearer sk-ant-api03-abcdef1234567890 and api_key='secret12345678'"
    redacted = redact_sensitive_text(text)
    assert "sk-ant-api03" not in redacted
    assert "secret12345678" not in redacted
    assert "[REDACTED_SECRET]" in redacted


def test_stream_broadcaster_independent_connection_sequences() -> None:
    registry = SessionRegistry()
    c1 = ConnectionContext("conn_1", "websocket", "2026-09-20T12:00:00Z")
    c2 = ConnectionContext("conn_2", "websocket", "2026-09-20T12:00:00Z")
    registry.register_connection(c1)
    registry.register_connection(c2)

    user = ClientIdentity("alice", "client_1", "desktop")
    registry.bind_connection_to_session("conn_1", "sess_alice", "conv_a", user)
    registry.bind_connection_to_session("conn_2", "sess_alice", "conv_a", user)
    registry.register_task_to_session("task_1", "sess_alice")

    broadcaster = StreamBroadcaster(registry)

    # Broadcast event
    enriched = EnrichedGatewayEvent.create(
        event_id="evt_101",
        event_type="plan.node_state_changed",
        payload={"task_id": "task_1", "node_id": "n1", "status": "RUNNING"},
        category=EventCategory.AUTHORITATIVE,
        sequence=SequenceTriad(global_seq=500, aggregate_version=5, connection_seq=0),
        timestamp_utc="2026-09-20T12:00:00Z",
    )

    count = broadcaster.broadcast_domain_event(enriched, task_id="task_1")
    assert count == 2

    # Verify each connection queue received its own connection_seq
    q1 = broadcaster.get_or_create_queue("conn_1")
    q2 = broadcaster.get_or_create_queue("conn_2")

    e1 = q1.pop()
    e2 = q2.pop()

    assert e1 is not None and e2 is not None
    assert e1.sequence.global_seq == 500
    assert e2.sequence.global_seq == 500
    assert e1.sequence.aggregate_version == 5
    assert e2.sequence.aggregate_version == 5
    assert e1.sequence.connection_seq == 1
    assert e2.sequence.connection_seq == 1


def test_authorization_before_projection() -> None:
    registry = SessionRegistry()
    conn_alice = ConnectionContext("conn_alice", "websocket", "2026-09-20T12:00:00Z")
    conn_bob = ConnectionContext("conn_bob", "websocket", "2026-09-20T12:00:00Z")
    registry.register_connection(conn_alice)
    registry.register_connection(conn_bob)

    alice = ClientIdentity("alice", "client_a", "desktop", "user")
    bob = ClientIdentity("bob", "client_b", "desktop", "user")
    registry.bind_connection_to_session("conn_alice", "sess_alice", "conv_a", alice)
    registry.bind_connection_to_session("conn_bob", "sess_bob", "conv_b", bob)
    registry.register_task_to_session("task_secret_alice", "sess_alice")

    broadcaster = StreamBroadcaster(registry)

    enriched = EnrichedGatewayEvent.create(
        event_id="evt_secret",
        event_type="task.completed",
        payload={"task_id": "task_secret_alice", "result": "private data"},
        category=EventCategory.AUTHORITATIVE,
        sequence=SequenceTriad(global_seq=77, aggregate_version=10, connection_seq=0),
        timestamp_utc="2026-09-20T12:00:00Z",
    )

    delivered = broadcaster.broadcast_domain_event(enriched, task_id="task_secret_alice")
    assert delivered == 1

    # Alice's queue received event; Bob's queue is empty
    q_alice = broadcaster.get_or_create_queue("conn_alice")
    q_bob = broadcaster.get_or_create_queue("conn_bob")

    assert len(q_alice) == 1
    assert len(q_bob) == 0


def test_backpressure_queue_telemetry_dropping() -> None:
    bq = BackpressureQueue("conn_slow", capacity=10, high_water_mark=5)

    # Push 5 Category A structural events
    for i in range(5):
        ev = EnrichedGatewayEvent.create(
            event_id=f"evt_struct_{i}",
            event_type="stage.changed",
            payload={"s": i},
            category=EventCategory.AUTHORITATIVE,
            sequence=SequenceTriad(i, i, i),
            timestamp_utc="2026-09-20T12:00:00Z",
        )
        assert bq.push(ev) is True

    # At high water mark (5): Category B telemetry should be dropped
    telemetry_ev = EnrichedGatewayEvent.create(
        event_id="evt_chunk_1",
        event_type="stdout_chunk",
        payload={"chunk": "working..."},
        category=EventCategory.TELEMETRY,
        sequence=SequenceTriad(6, 6, 6),
        timestamp_utc="2026-09-20T12:00:00Z",
    )
    assert bq.push(telemetry_ev) is False
    assert bq.dropped_telemetry_count == 1
    assert len(bq) == 5

    # But Category A event is still accepted up to capacity
    struct_ev_6 = EnrichedGatewayEvent.create(
        event_id="evt_struct_6",
        event_type="task.completed",
        payload={"done": True},
        category=EventCategory.AUTHORITATIVE,
        sequence=SequenceTriad(7, 7, 7),
        timestamp_utc="2026-09-20T12:00:00Z",
    )
    assert bq.push(struct_ev_6) is True
    assert len(bq) == 6
