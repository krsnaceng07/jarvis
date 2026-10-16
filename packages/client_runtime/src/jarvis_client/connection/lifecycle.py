"""Connection lifecycle state machine for Track 3.5.

13-state model tracking connection transitions, fatal states, and recovery triggers.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable


class ConnectionState(str, Enum):
    """Lifecycle state of client transport and session subscription."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    RESUMING = "resuming"
    CATCHING_UP = "catching_up"
    LIVE = "live"

    # Terminal or degraded states
    AUTH_FAILED = "auth_failed"
    AUTH_EXPIRED = "auth_expired"
    RESUME_FAILED = "resume_failed"
    PROTOCOL_INCOMPATIBLE = "protocol_incompatible"
    SERVER_UNAVAILABLE = "server_unavailable"
    RATE_LIMITED = "rate_limited"


class ConnectionLifecycle:
    """Manages connection transitions and notifies registered listeners."""

    def __init__(self, initial_state: ConnectionState = ConnectionState.DISCONNECTED) -> None:
        self._state = initial_state
        self._listeners: list[Callable[[ConnectionState, ConnectionState], None]] = []

    @property
    def current_state(self) -> ConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state in (
            ConnectionState.AUTHENTICATED,
            ConnectionState.RESUMING,
            ConnectionState.CATCHING_UP,
            ConnectionState.LIVE,
        )

    @property
    def is_live(self) -> bool:
        return self._state == ConnectionState.LIVE

    @property
    def is_fatal(self) -> bool:
        return self._state in (
            ConnectionState.AUTH_FAILED,
            ConnectionState.PROTOCOL_INCOMPATIBLE,
        )

    def transition_to(self, new_state: ConnectionState) -> None:
        """Atomically transition state and fire listeners if changed."""
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass

    def add_listener(self, listener: Callable[[ConnectionState, ConnectionState], None]) -> None:
        self._listeners.append(listener)


__all__ = ["ConnectionState", "ConnectionLifecycle"]
