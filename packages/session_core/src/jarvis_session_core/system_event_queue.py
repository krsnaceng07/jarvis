"""System Event Queue — holds pending state notices in memory.

Mirrors OpenClaw's system event queue semantics. Notices are held
in memory until dequeued during a session's context transformation.
If the gateway restarts, a startup sweep should re-materialize pending
notices from durable cursors, though this file provides the volatile
queue itself.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

logger = logging.getLogger("jarvis.sessions.system_event_queue")


class SystemEventQueue:
    """In-memory queue for system events per session.

    Dedupes based on `contextKey`. A frozen watermark notice is queued
    and remains pending until drained by the session.
    """

    def __init__(self) -> None:
        # Maps session_key -> list of event dicts
        self._queues: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def enqueue(self, message: str, options: dict[str, Any]) -> None:
        """Enqueue a system event for a specific session.

        Options must contain at least 'sessionKey'.
        'contextKey' is used to deduplicate pending notices.
        'replace' (bool) indicates if it should replace an existing notice with the same contextKey.
        """
        session_key = options.get("sessionKey")
        if not session_key:
            logger.warning("enqueue_system_event called without sessionKey")
            return

        context_key = options.get("contextKey")
        replace = options.get("replace", True)

        queue = self._queues[session_key]

        if context_key:
            # Dedupe based on contextKey
            for i, existing in enumerate(queue):
                if existing.get("contextKey") == context_key:
                    if replace:
                        queue[i] = {
                            "message": message,
                            "options": options,
                            "contextKey": context_key,
                        }
                    return

        # Not found or no contextKey, append
        queue.append({"message": message, "options": options, "contextKey": context_key})
        logger.debug("Enqueued system event for %s: %s...", session_key, message[:50])

    def dequeue(self, session_key: str) -> list[dict[str, Any]]:
        """Dequeue and return all pending system events for the session."""
        if session_key not in self._queues:
            return []

        events = self._queues.pop(session_key)
        if events:
            logger.debug("Dequeued %d system events for %s", len(events), session_key)
        return events


# Global singleton instance
_GLOBAL_QUEUE = SystemEventQueue()


def enqueue_system_event(message: str, options: dict[str, Any]) -> None:
    _GLOBAL_QUEUE.enqueue(message, options)


def dequeue_system_events(session_key: str) -> list[dict[str, Any]]:
    return _GLOBAL_QUEUE.dequeue(session_key)


def __getattr__(name: str) -> Any:
    if name == "GLOBAL_QUEUE":
        return _GLOBAL_QUEUE
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "SystemEventQueue",
    "dequeue_system_events",
    "enqueue_system_event",
]
