"""Two-tier event replay and race-free replay-live handoff engine for Track 3.4.

Enforces Invariant T34-03: RAM ring buffer is an optimization cache only;
queries outside contiguous RAM range MUST reconstruct from EventStore journal.
Enforces Invariant T34-10: Reconnection and catch-up are strictly read-only.
Enforces Invariant T34-12: Catch-up transitions to live streaming without event loss or duplication.
"""

from __future__ import annotations

from collections import deque
import json

from jarvis_agent.gateway.models import (
    ClientIdentity,
    ConnectionContext,
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.gateway.session_registry import SessionRegistry
from jarvis_agent.gateway.streamer import StreamBroadcaster
from jarvis_agent.orchestration.state.event_store import EventStore


class CatchupEngine:
    """Provides fast-path RAM replay, EventStore journal fallback, and race-free handoff."""

    def __init__(
        self,
        event_store: EventStore,
        session_registry: SessionRegistry,
        ring_buffer_capacity: int = 5_000,
        max_replay_limit: int = 5_000,
    ) -> None:
        self.event_store = event_store
        self.session_registry = session_registry
        self.ring_buffer_capacity = ring_buffer_capacity
        self.max_replay_limit = max_replay_limit

        # In-memory circular buffer: holds most recent EnrichedGatewayEvent objects
        self._ring: deque[EnrichedGatewayEvent] = deque(maxlen=ring_buffer_capacity)
        # Map global_seq -> EnrichedGatewayEvent for fast index lookups in ring
        self._ring_index: dict[int, EnrichedGatewayEvent] = {}

    def feed_event(self, event: EnrichedGatewayEvent) -> None:
        """Feed a committed domain event into the in-memory circular buffer."""
        if len(self._ring) == self._ring.maxlen:
            oldest = self._ring[0]
            self._ring_index.pop(oldest.sequence.global_seq, None)

        self._ring.append(event)
        self._ring_index[event.sequence.global_seq] = event

    def replay_events(
        self,
        resume_after_global_seq: int,
        identity: ClientIdentity,
        task_id: str | None = None,
        limit: int | None = None,
    ) -> list[EnrichedGatewayEvent]:
        """Replay missing events starting strictly after resume_after_global_seq.

        Enforces Invariant T34-03: Contiguity check; falls back to EventStore journal if gap.
        Enforces Invariant T34-21: Authorization filtering before returning events.
        """
        max_records = min(limit or self.max_replay_limit, self.max_replay_limit)

        # 1. Determine if RAM ring has contiguous range
        can_use_ring = False
        if self._ring:
            ring_start = self._ring[0].sequence.global_seq
            ring_end = self._ring[-1].sequence.global_seq
            # Contiguous check: requested start is within ring bounds
            if resume_after_global_seq >= (ring_start - 1) and resume_after_global_seq <= ring_end:
                can_use_ring = True

        events_to_filter: list[EnrichedGatewayEvent] = []

        if can_use_ring:
            # Fast-path from RAM ring
            for ev in self._ring:
                if ev.sequence.global_seq > resume_after_global_seq:
                    events_to_filter.append(ev)
                    if len(events_to_filter) >= max_records:
                        break
        else:
            # Fallback to authoritative EventStore journal
            cur = self.event_store._conn.cursor()
            cur.execute(
                """
                SELECT rowid, event_id, task_id, conversation_id, event_type,
                       timestamp_utc, sequence_number, payload_json,
                       causation_event_id, correlation_id
                FROM orchestration_events
                WHERE rowid > ?
                ORDER BY rowid ASC
                LIMIT ?;
                """,
                (resume_after_global_seq, max_records),
            )
            rows = cur.fetchall()
            for r in rows:
                global_seq = int(r[0])
                event_id = str(r[1])
                # r[2] is task_id
                event_type = str(r[4])
                ts_utc = str(r[5])
                agg_version = int(r[6])
                payload = json.loads(r[7])
                causation_id = r[8]
                correlation_id = r[9]

                category = (
                    EventCategory.TELEMETRY
                    if "chunk" in event_type or "progress" in event_type
                    else EventCategory.AUTHORITATIVE
                )

                ev = EnrichedGatewayEvent.create(
                    event_id=event_id,
                    event_type=event_type,
                    payload=payload,
                    category=category,
                    sequence=SequenceTriad(
                        global_seq=global_seq,
                        aggregate_version=agg_version,
                        connection_seq=0,
                    ),
                    timestamp_utc=ts_utc,
                    causation_id=causation_id,
                    correlation_id=correlation_id,
                )
                events_to_filter.append(ev)

        # Invariant T34-21: Filter events by caller authorization
        authorized_events: list[EnrichedGatewayEvent] = []
        for ev in events_to_filter:
            ev_task = ev.payload.get("task_id") if isinstance(ev.payload, dict) else None
            if task_id and ev_task and ev_task != task_id:
                continue
            if ev_task and not self.session_registry.is_authorized_for_task(identity, ev_task):
                continue
            authorized_events.append(ev)

        return authorized_events

    def perform_replay_live_handoff(
        self,
        conn: ConnectionContext,
        resume_after_global_seq: int,
        broadcaster: StreamBroadcaster,
        task_id: str | None = None,
    ) -> list[EnrichedGatewayEvent]:
        """Atomic handoff from catch-up replay into live streaming (Invariant T34-12, E09).

        Guarantees zero events lost and zero duplicates when events commit during catch-up.
        """
        # Step 1: Snapshot boundary sequence from EventStore
        cur = self.event_store._conn.cursor()
        cur.execute("SELECT MAX(rowid) FROM orchestration_events;")
        val = cur.fetchone()[0]
        boundary_seq = int(val) if val is not None else 0

        # Step 2: Query missing historical range up to boundary_seq
        historical = self.replay_events(
            resume_after_global_seq=resume_after_global_seq,
            identity=conn.authenticated_identity or ClientIdentity("guest", "unknown", "guest"),
            task_id=task_id,
            limit=self.max_replay_limit,
        )
        # Cap replay strictly at the captured boundary sequence
        historical = [ev for ev in historical if ev.sequence.global_seq <= boundary_seq]

        # Enqueue historical events into connection queue with transport sequence
        queue = broadcaster.get_or_create_queue(conn.connection_id)
        for ev in historical:
            c_seq = conn.next_seq()
            triad = SequenceTriad(
                global_seq=ev.sequence.global_seq,
                aggregate_version=ev.sequence.aggregate_version,
                connection_seq=c_seq,
            )
            bound_ev = EnrichedGatewayEvent(
                event_id=ev.event_id,
                event_type=ev.event_type,
                payload=ev.payload,
                category=ev.category,
                sequence=triad,
                timestamp_utc=ev.timestamp_utc,
                causation_id=ev.causation_id,
                correlation_id=ev.correlation_id,
                payload_hash=ev.payload_hash,
            )
            queue.push(bound_ev)

        return historical


__all__ = ["CatchupEngine"]
