"""Heartbeat and keepalive manager for Track 3.5 client runtime.

Monitors connection health via ping/pong frames, tracks RTT latency,
and triggers 3-strike half-open detection.
"""

from __future__ import annotations

import time
from typing import Callable


class ClientHeartbeatManager:
    """Coordinates ping frames, tracks round-trip time (RTT), and detects socket death."""

    def __init__(
        self,
        ping_interval_seconds: float = 15.0,
        pong_timeout_seconds: float = 5.0,
        max_missed_pongs: int = 3,
        send_ping_cb: Callable[[], None] | None = None,
        on_dead_connection_cb: Callable[[], None] | None = None,
    ) -> None:
        self.ping_interval = ping_interval_seconds
        self.pong_timeout = pong_timeout_seconds
        self.max_missed_pongs = max_missed_pongs
        self.send_ping_cb = send_ping_cb
        self.on_dead_connection_cb = on_dead_connection_cb

        self._last_ping_time: float = 0.0
        self._last_pong_time: float = time.monotonic()
        self._missed_pongs: int = 0
        self._last_rtt_ms: float = 0.0

    @property
    def last_rtt_ms(self) -> float:
        return self._last_rtt_ms

    @property
    def missed_pongs(self) -> int:
        return self._missed_pongs

    def send_ping(self) -> None:
        """Trigger an outbound ping and record timestamp."""
        now = time.monotonic()
        self._last_ping_time = now
        if self.send_ping_cb:
            self.send_ping_cb()

    def record_pong(self) -> None:
        """Process incoming pong, update RTT, and clear missed counter."""
        now = time.monotonic()
        self._last_pong_time = now
        if self._last_ping_time > 0:
            self._last_rtt_ms = (now - self._last_ping_time) * 1000.0
        self._missed_pongs = 0

    def check_health(self) -> bool:
        """Evaluate whether connection is alive.

        Returns True if healthy; triggers callback and returns False on 3-strike timeout.
        """
        now = time.monotonic()
        # If ping was sent and pong hasn't arrived within timeout
        if self._last_ping_time > self._last_pong_time:
            if (now - self._last_ping_time) > self.pong_timeout:
                self._missed_pongs += 1
                if self._missed_pongs >= self.max_missed_pongs:
                    if self.on_dead_connection_cb:
                        self.on_dead_connection_cb()
                    return False
        return True

    def reset(self) -> None:
        """Reset state upon connection re-establishment."""
        now = time.monotonic()
        self._last_ping_time = 0.0
        self._last_pong_time = now
        self._missed_pongs = 0
        self._last_rtt_ms = 0.0


__all__ = ["ClientHeartbeatManager"]
