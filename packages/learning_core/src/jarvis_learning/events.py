"""jarvis_learning.events — learning event types and internal event bus.

Defines typed events emitted by the learning system and a lightweight
in-process bus for internal subscribers.  This is separate from the
JARVIS HookBus (which is the runtime integration surface); the
learning event bus is for intra-learning-system communication.
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable

from .experience import now_ms

logger = logging.getLogger(__name__)


class LearningEventType(StrEnum):
    """Discriminated event types emitted by the learning system."""

    INTERACTION_STARTED = "interaction_started"
    INTENT_DETECTED = "intent_detected"
    PLAN_CREATED = "plan_created"
    TOOL_SELECTED = "tool_selected"
    TOOL_EXECUTED = "tool_executed"
    TOOL_SUCCEEDED = "tool_succeeded"
    TOOL_FAILED = "tool_failed"
    USER_CORRECTED = "user_corrected"
    USER_CONFIRMED_SUCCESS = "user_confirmed_success"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    MEMORY_RETRIEVED = "memory_retrieved"
    STRATEGY_USED = "strategy_used"
    STRATEGY_FAILED = "strategy_failed"
    EXPERIENCE_FINALIZED = "experience_finalized"
    LESSON_EXTRACTED = "lesson_extracted"
    TRAINING_SAMPLE_CREATED = "training_sample_created"
    MODEL_EVALUATED = "model_evaluated"
    MODEL_PROMOTED = "model_promoted"
    MODEL_ROLLED_BACK = "model_rolled_back"


@dataclass(frozen=True, slots=True)
class AgentContext:
    """Multi-agent isolation context propagating with learning events."""

    task_id: str
    session_id: str
    run_id: str
    agent_id: str
    turn_id: str = ""
    sequence_number: int = 0
    parent_agent_id: str | None = None
    channel_id: str | None = None  # e.g., "desktop", "telegram", "voice"
    workspace_id: str | None = None
    tool_call_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "agent_id": self.agent_id,
            "turn_id": self.turn_id,
            "sequence_number": self.sequence_number,
            "parent_agent_id": self.parent_agent_id,
            "channel_id": self.channel_id,
            "workspace_id": self.workspace_id,
            "tool_call_id": self.tool_call_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentContext:
        return cls(
            task_id=str(data.get("task_id") or data.get("taskId") or "default_task"),
            session_id=str(data.get("session_id") or data.get("sessionId") or "default_session"),
            run_id=str(data.get("run_id") or data.get("runId") or "default_run"),
            agent_id=str(data.get("agent_id") or data.get("agentId") or "default_agent"),
            turn_id=str(data.get("turn_id") or data.get("turnId") or ""),
            sequence_number=int(data.get("sequence_number") or data.get("sequenceNumber") or 0),
            parent_agent_id=data.get("parent_agent_id") or data.get("parentAgentId"),
            channel_id=data.get("channel_id") or data.get("channelId"),
            workspace_id=data.get("workspace_id") or data.get("workspaceId"),
            tool_call_id=data.get("tool_call_id") or data.get("toolCallId"),
        )


class EventIdempotencyStore:
    """Two-tier event idempotency: L1 in-memory TTL + L2 SQLite durable store."""

    def __init__(
        self,
        db: Any | None = None,
        ttl_seconds: float = 300.0,
        max_l1_entries: int = 10000,
    ) -> None:
        self._db = db
        self._ttl_seconds = ttl_seconds
        self._max_l1_entries = max_l1_entries
        self._l1_cache: dict[tuple[str, str], float] = {}
        import threading

        self._lock = threading.Lock()

    def set_db(self, db: Any) -> None:
        """Set or update the L2 SQLite backing database."""
        self._db = db

    def _prune_l1(self, now: float) -> None:
        if len(self._l1_cache) > self._max_l1_entries:
            expired = [k for k, exp in self._l1_cache.items() if exp <= now]
            for k in expired:
                del self._l1_cache[k]
            if len(self._l1_cache) > self._max_l1_entries:
                sorted_keys = sorted(self._l1_cache.items(), key=lambda x: x[1])
                for k, _ in sorted_keys[: len(sorted_keys) // 5]:
                    del self._l1_cache[k]

    def is_duplicate_and_record(
        self,
        agent_id: str,
        event_id: str,
        event_type: str = "generic",
    ) -> bool:
        """Check if event is duplicate, and record it if new.

        Returns:
            True if event was already processed (duplicate).
            False if event is new and was successfully recorded.
        """
        import time

        now = time.time()
        key = (agent_id, event_id)

        with self._lock:
            # 1. Check L1 in-memory cache
            if key in self._l1_cache:
                if self._l1_cache[key] > now:
                    return True
                del self._l1_cache[key]

            # 2. Check & record in L2 SQLite (if db configured)
            if self._db is not None and hasattr(self._db, "record_processed_event"):
                inserted = self._db.record_processed_event(
                    agent_id=agent_id,
                    event_id=event_id,
                    event_type=event_type,
                    processed_at=int(now * 1000),
                )
                if not inserted:
                    self._l1_cache[key] = now + self._ttl_seconds
                    return True

            # 3. Mark in L1 cache
            self._l1_cache[key] = now + self._ttl_seconds
            self._prune_l1(now)
            return False

    def is_duplicate(self, agent_id: str, event_id: str) -> bool:
        """Read-only check if event is duplicate."""
        import time

        now = time.time()
        key = (agent_id, event_id)

        with self._lock:
            if key in self._l1_cache and self._l1_cache[key] > now:
                return True
            if self._db is not None and hasattr(self._db, "has_processed_event"):
                return bool(self._db.has_processed_event(agent_id, event_id))
            return False

    def clear_l1(self) -> None:
        """Clear the L1 in-memory cache (for test isolation)."""
        with self._lock:
            self._l1_cache.clear()


@dataclass(frozen=True, slots=True)
class LearningEvent:
    """A single event in the learning lifecycle."""

    event_type: str
    timestamp: int
    data: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    event_id: str = ""
    agent_context: AgentContext | None = None


LearningCallback = Callable[[LearningEvent], Any]


class LearningEventBus:
    """Lightweight in-process event bus for learning system internals.

    Subscribers are keyed by event type.  Sync and async callbacks
    are both supported.  Exceptions in a subscriber are logged and
    swallowed — one bad subscriber never blocks the pipeline.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[LearningCallback]] = {}

    def subscribe(self, event_type: str, callback: LearningCallback) -> None:
        """Register a callback for an event type."""
        self._subscribers.setdefault(event_type, []).append(callback)

    def unsubscribe(self, event_type: str, callback: LearningCallback) -> None:
        """Remove a previously registered callback."""
        handlers = self._subscribers.get(event_type)
        if handlers is not None:
            try:
                handlers.remove(callback)
            except ValueError:
                pass

    def emit(self, event: LearningEvent) -> None:
        """Dispatch an event to all sync subscribers."""
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                result = handler(event)
                # If the handler returned a coroutine by accident, warn.
                if inspect.isawaitable(result):
                    logger.warning(
                        "async handler %s registered on sync emit path; use emit_async instead",
                        handler,
                    )
            except Exception:
                logger.exception(
                    "learning event handler %s failed for %s",
                    handler,
                    event.event_type,
                )

    async def emit_async(self, event: LearningEvent) -> None:
        """Dispatch an event, awaiting async subscribers."""
        handlers = self._subscribers.get(event.event_type, [])
        for handler in handlers:
            try:
                if inspect.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception:
                logger.exception(
                    "learning event handler %s failed for %s",
                    handler,
                    event.event_type,
                )

    def create_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
        source: str = "",
    ) -> LearningEvent:
        """Convenience: build and return (but don't emit) an event."""
        return LearningEvent(
            event_type=event_type,
            timestamp=now_ms(),
            data=data or {},
            source=source,
        )
