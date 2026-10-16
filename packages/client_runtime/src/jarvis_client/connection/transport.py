"""Transport abstraction for Track 3.5 client runtime.

Supports direct mock/loopback in-memory channels for deterministic testing
as well as standard Python WebSocket connections.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable


class ClientTransport(ABC):
    """Abstract interface for client transport adapters."""

    @abstractmethod
    def connect(self) -> None:
        """Establish transport connection."""

    @abstractmethod
    def send(self, message: str) -> None:
        """Send raw text frame."""

    @abstractmethod
    def close(self) -> None:
        """Close transport socket."""

    @abstractmethod
    def set_message_handler(self, handler: Callable[[str], None]) -> None:
        """Register handler for incoming messages."""

    @abstractmethod
    def set_disconnect_handler(self, handler: Callable[[str], None]) -> None:
        """Register handler for transport drops."""

    def receive_from_server(self, message: str) -> None:
        """Deliver server-pushed frame into client message handler (for loopback/simulation)."""
        raise NotImplementedError


class LoopbackTransport(ClientTransport):
    """In-memory synchronous loopback transport for deterministic testing."""

    def __init__(self, gateway_receiver: Callable[[str], str] | None = None) -> None:
        self.gateway_receiver = gateway_receiver
        self._msg_handler: Callable[[str], None] | None = None
        self._disc_handler: Callable[[str], None] | None = None
        self.is_connected: bool = False
        self.sent_frames: list[str] = []

    def connect(self) -> None:
        self.is_connected = True

    def send(self, message: str) -> None:
        if not self.is_connected:
            raise ConnectionError("Transport is disconnected.")
        self.sent_frames.append(message)
        if self.gateway_receiver:
            response = self.gateway_receiver(message)
            if response and self._msg_handler:
                self._msg_handler(response)

    def receive_from_server(self, message: str) -> None:
        """Deliver server-pushed frame (e.g. streaming event) into client."""
        if self.is_connected and self._msg_handler:
            self._msg_handler(message)

    def simulate_drop(self, reason: str = "Connection lost") -> None:
        """Simulate unexpected network drop."""
        self.is_connected = False
        if self._disc_handler:
            self._disc_handler(reason)

    def close(self) -> None:
        self.is_connected = False

    def set_message_handler(self, handler: Callable[[str], None]) -> None:
        self._msg_handler = handler

    def set_disconnect_handler(self, handler: Callable[[str], None]) -> None:
        self._disc_handler = handler


__all__ = ["ClientTransport", "LoopbackTransport"]
