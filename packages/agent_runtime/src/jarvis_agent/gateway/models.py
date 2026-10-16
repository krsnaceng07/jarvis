"""Canonical data contracts and protocol models for Track 3.4.

Defines client identity, connection context, event sequence triad,
resume cursors, stream classifications, and frame boundaries.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any, Literal

from jarvis_gateway_protocol.schema import (
    GatewayEvent,
    GatewayRequest,
    GatewayResponse,
    RPCError,
    RPCMethod,
    RPCRequest,
    RPCResponse,
)

# Frame size limits (bytes)
MAX_REQUEST_BYTES: int = 10 * 1024 * 1024  # 10 MB
MAX_EVENT_BYTES: int = 10 * 1024 * 1024  # 10 MB
MAX_STREAM_CHUNK_BYTES: int = 64 * 1024  # 64 KB
MAX_REPLAY_EVENTS_PER_BATCH: int = 5_000


class ConnectionState(str, Enum):
    """Lifecycle state of an external transport connection."""

    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    HEALTHY = "healthy"
    SUSPECTED_DEAD = "suspected_dead"
    CLOSING = "closing"
    CLOSED = "closed"


class EventCategory(str, Enum):
    """Classification of gateway stream events under backpressure."""

    AUTHORITATIVE = "authoritative"  # Category A: structural transitions (NEVER dropped)
    TELEMETRY = "telemetry"  # Category B: stdout/stderr chunks, typing (droppable)
    EVIDENCE = "evidence"  # Category C: cryptographic hashes, verifications (NEVER dropped)


class DeliveryStatus(str, Enum):
    """Delivery confirmation states for external channel transports."""

    CREATED = "created"
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    TRANSPORT_ACCEPTED = "transport_accepted"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ClientIdentity:
    """Authenticated principal establishing a connection."""

    user_id: str
    client_id: str
    client_type: str  # "desktop", "web", "telegram", "discord", "cli", "system"
    auth_tier: str = "user"  # "admin", "user", "guest", "service"
    scopes: frozenset[str] = field(default_factory=lambda: frozenset(["read", "write"]))
    session_grants: frozenset[str] = field(default_factory=frozenset)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "admin" in self.scopes

    def can_access_session(self, session_id: str) -> bool:
        if self.auth_tier == "admin":
            return True
        if not self.session_grants:
            return True  # Owner of dynamic sessions
        return session_id in self.session_grants

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "client_id": self.client_id,
            "client_type": self.client_type,
            "auth_tier": self.auth_tier,
            "scopes": sorted(list(self.scopes)),
            "session_grants": sorted(list(self.session_grants)),
        }


@dataclass(slots=True)
class ConnectionContext:
    """Active physical connection lifecycle tracking context."""

    connection_id: str
    transport_type: str  # "websocket", "ipc", "pipe", "mock"
    connected_at_utc: str
    authenticated_identity: ClientIdentity | None = None
    state: ConnectionState = ConnectionState.CONNECTED
    last_heartbeat_at_utc: str = ""
    seq_counter: int = 0
    assigned_session_id: str | None = None

    def next_seq(self) -> int:
        """Atomically increment and return the connection-scoped transport sequence."""
        self.seq_counter += 1
        return self.seq_counter


@dataclass(frozen=True, slots=True)
class SequenceTriad:
    """Explicit decoupling of journal, aggregate, and transport sequence numbers."""

    global_seq: int  # Authoritative EventStore journal index
    aggregate_version: int  # Task aggregate state revision
    connection_seq: int  # Transport connection sequence number

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ResumeCursor:
    """Durable resume cursor for replay queries."""

    journal_id: str
    global_seq: int
    aggregate_id: str | None = None
    aggregate_version: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResumeCursor:
        return cls(
            journal_id=str(data.get("journal_id", "default")),
            global_seq=int(data.get("global_seq", 0)),
            aggregate_id=data.get("aggregate_id"),
            aggregate_version=(
                int(data["aggregate_version"])
                if data.get("aggregate_version") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class StreamChunkPayload:
    """Typed execution chunk payload originating below the gateway."""

    task_id: str
    node_id: str
    stream_type: Literal["stdout", "stderr", "progress"]
    chunk: str
    timestamp_utc: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EnrichedGatewayEvent:
    """Complete gateway event frame embedding sequence triad and lineage correlation."""

    event_id: str
    event_type: str
    payload: Any
    category: EventCategory
    sequence: SequenceTriad
    timestamp_utc: str
    causation_id: str | None = None
    correlation_id: str | None = None
    payload_hash: str = ""

    def to_gateway_event(self) -> GatewayEvent:
        """Convert into canonical OpenClaw GatewayEvent envelope."""
        return GatewayEvent(
            event=self.event_type,
            payload=self.payload,
            seq=self.sequence.connection_seq,
            stateVersion=self.sequence.aggregate_version,
        )

    @classmethod
    def create(
        cls,
        event_id: str,
        event_type: str,
        payload: Any,
        category: EventCategory,
        sequence: SequenceTriad,
        timestamp_utc: str,
        causation_id: str | None = None,
        correlation_id: str | None = None,
    ) -> EnrichedGatewayEvent:
        serialized = json.dumps(payload, sort_keys=True, default=str)
        p_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        return cls(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            category=category,
            sequence=sequence,
            timestamp_utc=timestamp_utc,
            causation_id=causation_id,
            correlation_id=correlation_id,
            payload_hash=p_hash,
        )


__all__ = [
    "MAX_REQUEST_BYTES",
    "MAX_EVENT_BYTES",
    "MAX_STREAM_CHUNK_BYTES",
    "MAX_REPLAY_EVENTS_PER_BATCH",
    "ConnectionState",
    "EventCategory",
    "DeliveryStatus",
    "ClientIdentity",
    "ConnectionContext",
    "SequenceTriad",
    "ResumeCursor",
    "StreamChunkPayload",
    "EnrichedGatewayEvent",
    "GatewayEvent",
    "GatewayRequest",
    "GatewayResponse",
    "RPCError",
    "RPCMethod",
    "RPCRequest",
    "RPCResponse",
]
