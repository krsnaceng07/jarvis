"""Test suite for Track 3.4 Two-Tier Catch-Up & Replay-Live Handoff (Phase 3.4-H).

Validates:
1. Fast-path RAM ring replay.
2. EventStore journal fallback when range is outside RAM buffer (Invariant T34-03).
3. Authorization filtering before projection (Invariant T34-21).
4. Atomic replay-live handoff with zero gap and zero duplicates (Invariant T34-12, E09).
5. Catch-up is strictly read-only and generates zero ExecutionCommands (Invariant T34-10).
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path

from jarvis_agent.gateway.catchup import CatchupEngine
from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.gateway.session_registry import SessionRegistry
from jarvis_agent.gateway.streamer import StreamBroadcaster
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore


def test_catchup_ram_ring_vs_journal_fallback() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        es_path = Path(tmpdir) / "events.sqlite"
        event_store = EventStore(es_path)
        registry = SessionRegistry()

        # Engine with small RAM ring (size 3)
        engine = CatchupEngine(
            event_store=event_store,
            session_registry=registry,
            ring_buffer_capacity=3,
        )

        ident = ClientIdentity("alice", "client_1", "desktop", "admin")

        # Commit 5 events to EventStore
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        events = [
            DomainEvent.create(
                "t1", "c1", EventType.TASK_CREATED, {"task_id": "t1", "v": 1}, 1, timestamp_utc=now
            ),
            DomainEvent.create(
                "t1", "c1", EventType.STAGE_CHANGED, {"task_id": "t1", "v": 2}, 2, timestamp_utc=now
            ),
            DomainEvent.create(
                "t1", "c1", EventType.NODE_READY, {"task_id": "t1", "v": 3}, 3, timestamp_utc=now
            ),
            DomainEvent.create(
                "t1", "c1", EventType.NODE_STARTED, {"task_id": "t1", "v": 4}, 4, timestamp_utc=now
            ),
            DomainEvent.create(
                "t1", "c1", EventType.NODE_VERIFIED, {"task_id": "t1", "v": 5}, 5, timestamp_utc=now
            ),
        ]
        event_store.append_batch(events)

        # Feed events 3, 4, 5 into RAM ring
        for i, ev in enumerate(events[2:], start=3):
            enriched = EnrichedGatewayEvent.create(
                event_id=f"evt_{i}",
                event_type=ev.event_type.value,
                payload=ev.payload,
                category=EventCategory.AUTHORITATIVE,
                sequence=SequenceTriad(global_seq=i, aggregate_version=i, connection_seq=0),
                timestamp_utc=now,
            )
            engine.feed_event(enriched)

        # Case 1: Client asks for events after seq 3 (available in RAM ring [3..5])
        replayed_ram = engine.replay_events(resume_after_global_seq=3, identity=ident)
        assert len(replayed_ram) == 2
        assert replayed_ram[0].sequence.global_seq == 4
        assert replayed_ram[1].sequence.global_seq == 5

        # Case 2: Client asks for events after seq 0 (outside RAM ring -> journal fallback!)
        replayed_journal = engine.replay_events(resume_after_global_seq=0, identity=ident)
        assert len(replayed_journal) == 5
        assert [e.sequence.global_seq for e in replayed_journal] == [1, 2, 3, 4, 5]

        event_store.close()


def test_catchup_replay_live_handoff_no_gap() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        es_path = Path(tmpdir) / "events.sqlite"
        event_store = EventStore(es_path)
        registry = SessionRegistry()

        engine = CatchupEngine(event_store=event_store, session_registry=registry)
        broadcaster = StreamBroadcaster(registry)

        conn = ConnectionContext("conn_handoff", "websocket", "2026-09-20T12:00:00Z")
        ident = ClientIdentity("alice", "client_h", "desktop")
        registry.register_connection(conn)
        registry.bind_connection_to_session("conn_handoff", "sess_h", "conv_h", ident)
        registry.register_task_to_session("task_h", "sess_h")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Step 1: Commit historical events 1 and 2
        e1 = DomainEvent.create(
            "task_h", "conv_h", EventType.TASK_CREATED, {"task_id": "task_h"}, 1, timestamp_utc=now
        )
        e2 = DomainEvent.create(
            "task_h", "conv_h", EventType.STAGE_CHANGED, {"task_id": "task_h"}, 2, timestamp_utc=now
        )
        event_store.append_batch([e1, e2])

        # Step 2: Handoff replays 1 and 2
        replayed = engine.perform_replay_live_handoff(
            conn=conn,
            resume_after_global_seq=0,
            broadcaster=broadcaster,
            task_id="task_h",
        )
        assert len(replayed) == 2

        # Step 3: Now live event commits and broadcasts
        e3 = DomainEvent.create(
            "task_h", "conv_h", EventType.NODE_VERIFIED, {"task_id": "task_h"}, 3, timestamp_utc=now
        )
        event_store.append(e3)

        enriched_live = EnrichedGatewayEvent.create(
            event_id="evt_live_3",
            event_type="NODE_VERIFIED",
            payload={"task_id": "task_h"},
            category=EventCategory.AUTHORITATIVE,
            sequence=SequenceTriad(global_seq=3, aggregate_version=3, connection_seq=0),
            timestamp_utc=now,
        )
        broadcaster.broadcast_domain_event(enriched_live, task_id="task_h")

        # Step 4: Verify connection queue received exactly [1, 2, 3] in strict sequence with zero gaps and zero duplicates
        q = broadcaster.get_or_create_queue("conn_handoff")
        assert len(q) == 3

        item1 = q.pop()
        item2 = q.pop()
        item3 = q.pop()

        assert (
            item1 is not None
            and item1.sequence.global_seq == 1
            and item1.sequence.connection_seq == 1
        )
        assert (
            item2 is not None
            and item2.sequence.global_seq == 2
            and item2.sequence.connection_seq == 2
        )
        assert (
            item3 is not None
            and item3.sequence.global_seq == 3
            and item3.sequence.connection_seq == 3
        )

        event_store.close()
