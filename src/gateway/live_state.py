"""Gateway live state — active sessions, channel connectivity, and subscriptions in JARVIS."""

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

    async def emit_rpc_event(self, method: str, params: dict[str, Any]) -> None:
        """Broadcast a JSON-RPC 2.0 event frame (e.g. event.agent.draft)."""
        await self.subscriptions.broadcast(method, params)

    async def emit_agent_draft(self, session_key: str, delta: str) -> None:
        """Emit a progressive draft preview event (event.agent.draft)."""
        await self.emit_rpc_event("event.agent.draft", {"sessionKey": session_key, "delta": delta})


GLOBAL_GATEWAY_LIVE_STATE = GatewayLiveState()

__all__ = ["GLOBAL_GATEWAY_LIVE_STATE", "GatewayLiveState"]

