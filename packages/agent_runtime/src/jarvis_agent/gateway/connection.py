"""Connection state machine and heartbeat health tracking for Track 3.4."""

from __future__ import annotations

import datetime

from jarvis_agent.gateway.models import (
    ConnectionContext,
    ConnectionState,
)


class ConnectionLifecycleTracker:
    """Manages heartbeat health and state machine transitions for physical connections."""

    def __init__(
        self,
        ping_interval_seconds: float = 20.0,
        pong_timeout_seconds: float = 10.0,
        max_missed_pongs: int = 3,
    ) -> None:
        self.ping_interval_seconds = ping_interval_seconds
        self.pong_timeout_seconds = pong_timeout_seconds
        self.max_missed_pongs = max_missed_pongs
        # connection_id -> count of missed pings
        self._missed_pings: dict[str, int] = {}
        # connection_id -> timestamp of last sent ping
        self._last_ping_sent: dict[str, float] = {}

    def record_ping_sent(self, connection_id: str, timestamp: float) -> None:
        """Record that a ping frame was dispatched to the connection."""
        self._last_ping_sent[connection_id] = timestamp
        self._missed_pings[connection_id] = self._missed_pings.get(connection_id, 0) + 1

    def record_pong_received(self, conn: ConnectionContext, timestamp: float) -> None:
        """Record received pong response, resetting missed ping counter."""
        self._missed_pings[conn.connection_id] = 0
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn.last_heartbeat_at_utc = now_utc
        if conn.state in (ConnectionState.AUTHENTICATED, ConnectionState.SUSPECTED_DEAD):
            conn.state = ConnectionState.HEALTHY

    def evaluate_connection_health(
        self,
        conn: ConnectionContext,
        current_time: float,
    ) -> ConnectionState:
        """Evaluate if connection is healthy, suspected dead, or should be closed."""
        if conn.state == ConnectionState.CLOSED:
            return ConnectionState.CLOSED

        missed = self._missed_pings.get(conn.connection_id, 0)
        if missed >= self.max_missed_pongs:
            conn.state = ConnectionState.CLOSING
            return ConnectionState.CLOSING
        elif missed >= 1:
            conn.state = ConnectionState.SUSPECTED_DEAD
            return ConnectionState.SUSPECTED_DEAD

        return conn.state

    def cleanup_connection(self, connection_id: str) -> None:
        """Remove connection from heartbeat tracking."""
        self._missed_pings.pop(connection_id, None)
        self._last_ping_sent.pop(connection_id, None)


__all__ = ["ConnectionLifecycleTracker"]
