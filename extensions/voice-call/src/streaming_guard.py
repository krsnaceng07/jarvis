"""Connection tracking and rate limits for Media Streams streaming WebSockets."""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass(slots=True)
class StreamingConnectionCaps:
    pre_start_timeout_ms: int = 5000
    max_pending_connections: int = 32
    max_pending_connections_per_ip: int = 4
    max_connections: int = 128


class StreamingConnectionTracker:
    """Enforces streaming connection caps and pre-start handshake timeouts."""

    def __init__(self, caps: StreamingConnectionCaps | None = None) -> None:
        self.caps = caps or StreamingConnectionCaps()
        self._pending_connections: dict[str, tuple[str, float]] = {}  # conn_id -> (ip, timestamp)
        self._active_connections: dict[str, str] = {}  # conn_id -> ip

    @property
    def total_open_connections(self) -> int:
        return len(self._pending_connections) + len(self._active_connections)

    def count_pending_for_ip(self, ip: str) -> int:
        return sum(1 for (conn_ip, _) in self._pending_connections.values() if conn_ip == ip)

    def prune_expired_pending(self, now: float | None = None) -> list[str]:
        """Prune connections that exceeded preStartTimeoutMs before sending start frame."""
        current_time = now or time.time()
        timeout_sec = self.caps.pre_start_timeout_ms / 1000.0
        expired = []
        for conn_id, (_, start_time) in list(self._pending_connections.items()):
            if current_time - start_time > timeout_sec:
                expired.append(conn_id)
                self._pending_connections.pop(conn_id, None)
        return expired

    def can_accept(self, remote_ip: str) -> tuple[bool, str | None]:
        """Check whether a new pre-start connection can be accepted."""
        self.prune_expired_pending()

        if self.total_open_connections >= self.caps.max_connections:
            return False, f"max-connections-exceeded:{self.caps.max_connections}"

        if len(self._pending_connections) >= self.caps.max_pending_connections:
            return False, f"max-pending-connections-exceeded:{self.caps.max_pending_connections}"

        if self.count_pending_for_ip(remote_ip) >= self.caps.max_pending_connections_per_ip:
            return False, f"max-pending-per-ip-exceeded:{self.caps.max_pending_connections_per_ip}"

        return True, None

    def register_pending(self, connection_id: str, remote_ip: str) -> None:
        self._pending_connections[connection_id] = (remote_ip, time.time())

    def mark_started(self, connection_id: str) -> bool:
        """Promote connection from pending to active once start frame is received."""
        if connection_id in self._pending_connections:
            ip, _ = self._pending_connections.pop(connection_id)
            self._active_connections[connection_id] = ip
            return True
        return False

    def close_connection(self, connection_id: str) -> None:
        self._pending_connections.pop(connection_id, None)
        self._active_connections.pop(connection_id, None)
