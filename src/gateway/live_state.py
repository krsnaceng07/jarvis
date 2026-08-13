"""Gateway live state — mirrors OpenClaw ``src/gateway/server/server-live-state.ts``."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .subscriptions import SubscriptionRegistry

SessionMetadata = dict[str, object]
ActiveSessionMap = dict[str, SessionMetadata]
ChannelStatusMap = dict[str, bool]
TaskSet = set[str]


@dataclass
class GatewayLiveState:
    """Maintains active sessions, channel connectivity, and background execution state."""

    active_sessions: ActiveSessionMap = field(default_factory=dict)
    channel_status: ChannelStatusMap = field(default_factory=dict)
    running_tasks: TaskSet = field(default_factory=set)
    subscriptions: SubscriptionRegistry = field(default_factory=SubscriptionRegistry)

    def set_session_active(self, session_id: str, metadata: dict[str, Any] | None = None) -> None:
        self.active_sessions[session_id] = {
            "session_id": session_id,
            "connected_at": time.time(),
            "metadata": metadata or {},
        }

    def remove_session(self, session_id: str) -> None:
        self.active_sessions.pop(session_id, None)

    def set_channel_status(self, channel_id: str, connected: bool) -> None:
        self.channel_status[channel_id] = connected

    def set_task_running(self, task_id: str, running: bool) -> None:
        if running:
            self.running_tasks.add(task_id)
        else:
            self.running_tasks.discard(task_id)

    def is_task_running(self, task_id: str) -> bool:
        return task_id in self.running_tasks

    async def emit_event(self, topic: str, payload: dict[str, Any]) -> None:
        await self.subscriptions.broadcast(topic, payload)


GLOBAL_GATEWAY_LIVE_STATE = GatewayLiveState()

__all__ = ["GLOBAL_GATEWAY_LIVE_STATE", "GatewayLiveState"]
