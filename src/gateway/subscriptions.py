"""Gateway subscription registry — mirrors OpenClaw ``src/gateway/server/server-node-subscriptions.ts``."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable, Awaitable

_log = logging.getLogger("jarvis.gateway.subscriptions")


class SubscriptionRegistry:
    """Manages WebSocket client topic subscriptions."""

    def __init__(self) -> None:
        # topic -> set of send_coroutine_callbacks
        self._topics: dict[str, set[Callable[[dict[str, Any]], Awaitable[None]]]] = defaultdict(set)

    def subscribe(self, topic: str, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        self._topics[topic].add(callback)
        _log.debug("Subscribed callback to topic '%s'", topic)

    def unsubscribe(self, topic: str, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        if topic in self._topics:
            self._topics[topic].discard(callback)

    def unsubscribe_all(self, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        for subscribers in self._topics.values():
            subscribers.discard(callback)

    async def broadcast(self, topic: str, payload: dict[str, Any]) -> None:
        subscribers = list(self._topics.get(topic, set()))
        if not subscribers:
            return

        event = {"topic": topic, "data": payload}
        for cb in subscribers:
            try:
                await cb(event)
            except Exception as e:
                _log.debug("Broadcast to subscriber failed on topic '%s': %s", topic, e)


__all__ = ["SubscriptionRegistry"]
