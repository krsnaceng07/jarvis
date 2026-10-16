"""Event streaming, sequence assignment, secret redaction, and fan-out for Track 3.4.

Enforces Invariant T34-04: connection_seq, global_seq, and aggregate_version are strictly distinct.
Enforces Invariant T34-16: Event identity, causation, and correlation are preserved.
Enforces Invariant T34-21: Authorization check before projecting events to a client.
Enforces Invariant T34-22: Secrets are scrubbed from telemetry chunks before client projection.
"""

from __future__ import annotations

from typing import Callable

from jarvis_agent.gateway.backpressure import BackpressureQueue
from jarvis_agent.gateway.models import (
    EnrichedGatewayEvent,
    EventCategory,
    SequenceTriad,
)
from jarvis_agent.gateway.redactor import redact_sensitive_text
from jarvis_agent.gateway.session_registry import SessionRegistry


class StreamBroadcaster:
    """Manages event fan-out, per-connection sequencing, and telemetry redaction."""

    def __init__(self, session_registry: SessionRegistry) -> None:
        self.session_registry = session_registry
        # connection_id -> BackpressureQueue
        self._queues: dict[str, BackpressureQueue] = {}
        # Optional ring buffer hook for catch-up engine
        self.on_event_projected: Callable[[EnrichedGatewayEvent], None] | None = None

    def get_or_create_queue(self, connection_id: str) -> BackpressureQueue:
        if connection_id not in self._queues:
            self._queues[connection_id] = BackpressureQueue(connection_id=connection_id)
        return self._queues[connection_id]

    def remove_connection(self, connection_id: str) -> None:
        self._queues.pop(connection_id, None)

    def broadcast_domain_event(
        self, enriched: EnrichedGatewayEvent, task_id: str | None = None
    ) -> int:
        """Broadcast domain event to all authorized active connections.

        Returns number of connections the event was delivered to.
        """
        # Scrub secrets from telemetry deltas
        if enriched.category == EventCategory.TELEMETRY:
            payload = enriched.payload
            if isinstance(payload, dict) and "chunk" in payload:
                scrubbed = dict(payload)
                scrubbed["chunk"] = redact_sensitive_text(str(payload["chunk"]))
                enriched = EnrichedGatewayEvent(
                    event_id=enriched.event_id,
                    event_type=enriched.event_type,
                    payload=scrubbed,
                    category=enriched.category,
                    sequence=enriched.sequence,
                    timestamp_utc=enriched.timestamp_utc,
                    causation_id=enriched.causation_id,
                    correlation_id=enriched.correlation_id,
                    payload_hash=enriched.payload_hash,
                )

        if self.on_event_projected:
            self.on_event_projected(enriched)

        delivered_count = 0
        resolved_task_id = task_id or (
            enriched.payload.get("task_id") if isinstance(enriched.payload, dict) else None
        )

        for conn_id, conn in list(self.session_registry._connections.items()):
            if not conn.authenticated_identity:
                continue

            # Invariant T34-21: Authorization before projection
            if resolved_task_id and not self.session_registry.is_authorized_for_task(
                conn.authenticated_identity, resolved_task_id
            ):
                continue

            # Filter by session if assigned
            target_sess = conn.assigned_session_id
            if target_sess and resolved_task_id:
                task_sess = self.session_registry._task_sessions.get(resolved_task_id)
                if task_sess and task_sess != target_sess:
                    continue

            # Assign per-connection monotonic transport sequence (Invariant T34-04)
            c_seq = conn.next_seq()
            conn_triad = SequenceTriad(
                global_seq=enriched.sequence.global_seq,
                aggregate_version=enriched.sequence.aggregate_version,
                connection_seq=c_seq,
            )

            conn_event = EnrichedGatewayEvent(
                event_id=enriched.event_id,
                event_type=enriched.event_type,
                payload=enriched.payload,
                category=enriched.category,
                sequence=conn_triad,
                timestamp_utc=enriched.timestamp_utc,
                causation_id=enriched.causation_id,
                correlation_id=enriched.correlation_id,
                payload_hash=enriched.payload_hash,
            )

            queue = self.get_or_create_queue(conn_id)
            if queue.push(conn_event):
                delivered_count += 1

        return delivered_count


__all__ = ["StreamBroadcaster"]
