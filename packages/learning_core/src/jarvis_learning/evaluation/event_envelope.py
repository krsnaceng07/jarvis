"""jarvis_learning.evaluation.event_envelope — Canonical Immutable Event Envelope.

Enforces:
1. Complete canonical event contract across 23 strongly typed fields.
2. Dual timestamps: timestamp_monotonic (runtime decisions/SLOs) and timestamp_wallclock (audit).
3. Explicit event priority classes: P0_CRITICAL, P1_HIGH, P2_NORMAL, P3_LOW.
4. Deterministic SHA-256 payload digest and serialization/deserialization methods.
"""

from __future__ import annotations

import enum
import hashlib
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


class EventPriority(enum.StrEnum):
    """Priority tiers for shadow event dispatch, shedding, and durability."""

    P0_CRITICAL = "P0_CRITICAL"  # Safety violations, destructive attempts, rollback evidence
    P1_HIGH = "P1_HIGH"  # Tool failures, user corrections, turn cancellations, model disagreement
    P2_NORMAL = "P2_NORMAL"  # Ordinary tool execution, ordinary assistant response
    P3_LOW = "P3_LOW"  # Background telemetry, redundant heartbeats, low-value trace details


class CanonicalEventType(enum.StrEnum):
    """Canonical event types produced across the active assistant turn lifecycle."""

    USER_TURN_STARTED = "UserTurnStarted"
    USER_TURN_FINALIZED = "UserTurnFinalized"
    MODEL_DECISION_CREATED = "ModelDecisionCreated"
    TOOL_CALL_REQUESTED = "ToolCallRequested"
    TOOL_CALL_AUTHORIZED = "ToolCallAuthorized"
    TOOL_CALL_EXECUTED = "ToolCallExecuted"
    TOOL_RESULT_RECEIVED = "ToolResultReceived"
    ASSISTANT_RESPONSE_COMMITTED = "AssistantResponseCommitted"
    TURN_CANCELLED = "TurnCancelled"
    TURN_FAILED = "TurnFailed"
    TURN_COMPLETED = "TurnCompleted"


@dataclass(frozen=True, slots=True)
class CanonicalEventEnvelope:
    """Canonical immutable event envelope dispatched from active runtime to event bus."""

    event_id: str
    conversation_id: str
    session_id: str
    turn_id: str
    task_id: str
    task_generation: int
    parent_event_id: str
    event_type: str
    priority: str
    timestamp_monotonic: float
    timestamp_wallclock: float
    model_id: str
    model_version: str
    runtime_contract_digest: str
    tool_name: str
    sanitized_arguments: dict[str, Any]
    sanitized_context_digest: str
    active_policy_version: str
    active_tool_registry_digest: str
    active_state_version: int
    cancellation_state: str  # "ACTIVE", "CANCELLED", "COMPLETED"
    source_process_id: int
    source_thread_id: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_digest(self) -> str:
        """Compute deterministic RFC-compliant SHA-256 digest of envelope payload."""
        payload = {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "task_id": self.task_id,
            "task_generation": self.task_generation,
            "event_type": self.event_type,
            "priority": self.priority,
            "model_id": self.model_id,
            "tool_name": self.tool_name,
            "arguments": self.sanitized_arguments,
            "context_digest": self.sanitized_context_digest,
            "cancellation_state": self.cancellation_state,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Convert envelope to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize envelope to JSON string."""
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CanonicalEventEnvelope:
        """Deserialize envelope from mapping."""
        return cls(
            event_id=str(data["event_id"]),
            conversation_id=str(data.get("conversation_id", "")),
            session_id=str(data.get("session_id", "default")),
            turn_id=str(data.get("turn_id", "")),
            task_id=str(data.get("task_id", "")),
            task_generation=int(data.get("task_generation", 0)),
            parent_event_id=str(data.get("parent_event_id", "")),
            event_type=str(data.get("event_type", CanonicalEventType.USER_TURN_STARTED)),
            priority=str(data.get("priority", EventPriority.P2_NORMAL)),
            timestamp_monotonic=float(data.get("timestamp_monotonic", time.monotonic())),
            timestamp_wallclock=float(data.get("timestamp_wallclock", time.time())),
            model_id=str(data.get("model_id", "active_default")),
            model_version=str(data.get("model_version", "1.0.0")),
            runtime_contract_digest=str(data.get("runtime_contract_digest", "")),
            tool_name=str(data.get("tool_name", "")),
            sanitized_arguments=dict(data.get("sanitized_arguments", {})),
            sanitized_context_digest=str(data.get("sanitized_context_digest", "")),
            active_policy_version=str(data.get("active_policy_version", "1.0.0")),
            active_tool_registry_digest=str(data.get("active_tool_registry_digest", "")),
            active_state_version=int(data.get("active_state_version", 0)),
            cancellation_state=str(data.get("cancellation_state", "ACTIVE")),
            source_process_id=int(data.get("source_process_id", os.getpid())),
            source_thread_id=int(data.get("source_thread_id", threading.get_ident())),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def from_json(cls, json_str: str) -> CanonicalEventEnvelope:
        """Deserialize envelope from JSON string."""
        return cls.from_dict(json.loads(json_str))


def create_event_envelope(
    *,
    event_type: str | CanonicalEventType,
    priority: str | EventPriority = EventPriority.P2_NORMAL,
    conversation_id: str = "",
    session_id: str = "desktop:hud",
    turn_id: str = "",
    task_id: str = "",
    task_generation: int = 0,
    parent_event_id: str = "",
    model_id: str = "gemini-live-active",
    model_version: str = "1.0.0",
    runtime_contract_digest: str = "",
    tool_name: str = "",
    sanitized_arguments: dict[str, Any] | None = None,
    sanitized_context_digest: str = "",
    active_policy_version: str = "1.0.0",
    active_tool_registry_digest: str = "",
    active_state_version: int = 0,
    cancellation_state: str = "ACTIVE",
    metadata: dict[str, Any] | None = None,
) -> CanonicalEventEnvelope:
    """Convenience constructor populating monotonic and wall-clock times and PID/thread IDs."""
    now_mono = time.monotonic()
    now_wall = time.time()
    return CanonicalEventEnvelope(
        event_id=f"evt_{uuid.uuid4().hex[:12]}",
        conversation_id=conversation_id,
        session_id=session_id,
        turn_id=turn_id or f"turn_{uuid.uuid4().hex[:8]}",
        task_id=task_id,
        task_generation=task_generation,
        parent_event_id=parent_event_id,
        event_type=str(event_type),
        priority=str(priority),
        timestamp_monotonic=now_mono,
        timestamp_wallclock=now_wall,
        model_id=model_id,
        model_version=model_version,
        runtime_contract_digest=runtime_contract_digest,
        tool_name=tool_name,
        sanitized_arguments=sanitized_arguments or {},
        sanitized_context_digest=sanitized_context_digest,
        active_policy_version=active_policy_version,
        active_tool_registry_digest=active_tool_registry_digest,
        active_state_version=active_state_version,
        cancellation_state=cancellation_state,
        source_process_id=os.getpid(),
        source_thread_id=threading.get_ident(),
        metadata=metadata or {},
    )
