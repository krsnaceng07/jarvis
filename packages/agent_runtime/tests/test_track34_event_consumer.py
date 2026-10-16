"""Test suite for Track 3.4 Durable Event Consumer & Cursor Store (Phase 3.4-F).

Validates:
1. Committed EventStore polling using durable SQLite cursors.
2. Post-restart recovery resuming from last committed global sequence (Invariant T34-11).
3. Advisory notifications triggering event dispatch without data loss (Invariant T34-02).
4. Event deduplication preventing duplicate event emission.
5. GatewaySingletonLock mutual exclusion between processes.
"""

from __future__ import annotations

import datetime
import tempfile
from pathlib import Path
import pytest

from jarvis_agent.gateway.errors import GatewayErrorCode, GatewayException
from jarvis_agent.gateway.event_consumer import (
    GatewayEventConsumer,
    GatewayEventCursorStore,
)
from jarvis_agent.gateway.models import EnrichedGatewayEvent
from jarvis_agent.gateway.singleton import GatewaySingletonLock
from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore


def test_durable_event_consumer_cursor_recovery() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        es_path = Path(tmpdir) / "events.sqlite"
        cs_path = Path(tmpdir) / "cursors.sqlite"

        event_store = EventStore(es_path)
        cursor_store = GatewayEventCursorStore(cs_path)

        try:
            received_events: list[EnrichedGatewayEvent] = []
            consumer = GatewayEventConsumer(
                event_store=event_store,
                cursor_store=cursor_store,
                consumer_id="worker_1",
            )
            consumer.register_listener(lambda e: received_events.append(e))

            now_str = datetime.datetime.now(datetime.timezone.utc).isoformat()

            # 1. Commit 3 events to EventStore
            e1 = DomainEvent.create(
                "task_1", "conv_1", EventType.TASK_CREATED, {"g": 1}, 1, timestamp_utc=now_str
            )
            e2 = DomainEvent.create(
                "task_1",
                "conv_1",
                EventType.STAGE_CHANGED,
                {"stage": "PLANNING"},
                2,
                timestamp_utc=now_str,
            )
            e3 = DomainEvent.create(
                "task_2", "conv_2", EventType.TASK_CREATED, {"g": 2}, 1, timestamp_utc=now_str
            )
            event_store.append_batch([e1, e2, e3])

            # 2. Advisory wake-up dispatches all 3
            count = consumer.notify_committed()
            assert count == 3
            assert len(received_events) == 3
            assert received_events[0].sequence.global_seq == 1
            assert received_events[1].sequence.global_seq == 2
            assert received_events[2].sequence.global_seq == 3

            # Cursor updated in database
            assert cursor_store.get_cursor("worker_1") == 3

            # 3. Simulate process restart: new consumer on same DB
            received_after_restart: list[EnrichedGatewayEvent] = []
            c2 = GatewayEventConsumer(
                event_store=event_store,
                cursor_store=cursor_store,
                consumer_id="worker_1",
            )
            c2.register_listener(lambda e: received_after_restart.append(e))

            # Polling immediately finds 0 unconsumed events
            assert c2.poll_committed_events() == 0

            # Commit 4th event
            e4 = DomainEvent.create(
                "task_2",
                "conv_2",
                EventType.STAGE_CHANGED,
                {"stage": "EXECUTION"},
                2,
                timestamp_utc=now_str,
            )
            event_store.append(e4)

            # Poll finds only the 4th event
            assert c2.poll_committed_events() == 1
            assert len(received_after_restart) == 1
            assert received_after_restart[0].sequence.global_seq == 4
            assert cursor_store.get_cursor("worker_1") == 4
        finally:
            cursor_store.close()
            event_store.close()


def test_gateway_singleton_lock() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "singleton.sqlite"
        l1 = GatewaySingletonLock(lock_path, lease_ttl_seconds=5.0)
        l2 = GatewaySingletonLock(lock_path, lease_ttl_seconds=5.0)

        try:
            # Process 1 acquires lease
            assert l1.acquire_lease("proc_alpha") is True

            # Process 2 attempts acquisition -> SESSION_FORBIDDEN
            with pytest.raises(GatewayException) as exc:
                l2.acquire_lease("proc_beta")
            assert exc.value.code == GatewayErrorCode.SESSION_FORBIDDEN

            # Process 1 releases lease -> Process 2 acquires
            l1.release_lease("proc_alpha")
            assert l2.acquire_lease("proc_beta") is True
        finally:
            l1.close()
            l2.close()
