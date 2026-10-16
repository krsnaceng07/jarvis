"""Persistent event sourcing, pure state reduction, and crash recovery."""

from __future__ import annotations

from jarvis_agent.orchestration.state.event import DomainEvent, EventType
from jarvis_agent.orchestration.state.event_store import EventStore
from jarvis_agent.orchestration.state.recovery import CrashRecoveryManager
from jarvis_agent.orchestration.state.reducer import (
    RuntimeState,
    reduce_events,
    reduce_state,
)
from jarvis_agent.orchestration.state.snapshot import SnapshotEngine

__all__ = [
    "CrashRecoveryManager",
    "DomainEvent",
    "EventStore",
    "EventType",
    "RuntimeState",
    "SnapshotEngine",
    "reduce_events",
    "reduce_state",
]
