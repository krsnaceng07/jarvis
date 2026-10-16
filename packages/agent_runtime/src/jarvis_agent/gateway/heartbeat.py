"""Heartbeat manager running periodic connection health sweeps for Track 3.4."""

from __future__ import annotations

import time
from typing import Callable

from jarvis_agent.gateway.connection import ConnectionLifecycleTracker
from jarvis_agent.gateway.models import ConnectionContext, ConnectionState
from jarvis_agent.gateway.session_registry import SessionRegistry


class HeartbeatManager:
    """Coordinates ping frames, pong validation, and stale socket reaping."""

    def __init__(
        self,
        session_registry: SessionRegistry,
        tracker: ConnectionLifecycleTracker | None = None,
        ping_sender: Callable[[ConnectionContext], None] | None = None,
        close_handler: Callable[[ConnectionContext], None] | None = None,
    ) -> None:
        self.session_registry = session_registry
        self.tracker = tracker or ConnectionLifecycleTracker()
        self.ping_sender = ping_sender
        self.close_handler = close_handler

    def check_all_connections(self, now: float | None = None) -> list[str]:
        """Sweep all registered connections: send pings, detect half-open sockets, and reap closed ones."""
        curr_time = now if now is not None else time.monotonic()
        reaped_conn_ids: list[str] = []

        # Iterate over copy of registered connections
        for conn_id, conn in list(self.session_registry._connections.items()):
            state = self.tracker.evaluate_connection_health(conn, curr_time)
            if state == ConnectionState.CLOSING:
                if self.close_handler:
                    self.close_handler(conn)
                self.session_registry.unregister_connection(conn_id)
                self.tracker.cleanup_connection(conn_id)
                reaped_conn_ids.append(conn_id)
            else:
                # Dispatch ping
                self.tracker.record_ping_sent(conn_id, curr_time)
                if self.ping_sender:
                    self.ping_sender(conn)

        return reaped_conn_ids

    def handle_pong(self, connection_id: str, now: float | None = None) -> None:
        """Handle inbound pong response from client."""
        curr_time = now if now is not None else time.monotonic()
        conn = self.session_registry.get_connection(connection_id)
        if conn:
            self.tracker.record_pong_received(conn, curr_time)


__all__ = ["HeartbeatManager"]
