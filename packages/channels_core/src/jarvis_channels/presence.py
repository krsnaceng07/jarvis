"""Channel presence — typing indicators and status reactions.

Mirrors OpenClaw's ``src/channels/typing.ts`` +
``src/channels/status-reactions.ts``.

Provides a ``PresenceEmitter`` that channel plugins use to show a
"typing..." indicator while the agent is processing, and to react to
messages (e.g. 👍 thumbs up on receipt).

Phase W1: sync-only surface. Async variant (for real-time streaming
indicators) lands in Wave 3 when the live session is wired.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

_log = logging.getLogger("jarvis_channels.presence")


# ── Presence emitter ───────────────────────────────────────────────────


class PresenceEmitter:
    """Sends typing indicators and reactions to a channel.

    Mirrors OpenClaw's ``TypingIndicator`` class from
    ``src/channels/typing.ts``.

    Usage::

        emitter = PresenceEmitter(send_typing_fn, conversation_id)
        emitter.start()        # start showing "typing..."
        # ... agent processes ...
        emitter.stop()         # clear the indicator

    The emitter fires ``send_typing_fn(conversation_id)`` on a background
    thread at ``interval_sec`` intervals. Most channels auto-clear the
    indicator after ~5 seconds so we repeat until stopped.
    """

    def __init__(
        self,
        send_fn: Callable[[str], Any],
        conversation_id: str,
        *,
        interval_sec: float = 4.0,
    ) -> None:
        self._send_fn = send_fn
        self._conversation_id = conversation_id
        self._interval_sec = max(0.5, interval_sec)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the typing indicator loop in a daemon thread."""
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name=f"jarvis-typing-{self._conversation_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the typing indicator loop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_sec + 1)
            self._thread = None

    def __enter__(self) -> "PresenceEmitter":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()

    def _loop(self) -> None:
        """Send typing action repeatedly until stopped."""
        while not self._stop_event.is_set():
            try:
                self._send_fn(self._conversation_id)
            except Exception as e:  # noqa: BLE001
                _log.debug("presence: send_fn error: %s", e)
            self._stop_event.wait(self._interval_sec)


# ── Status reactions ───────────────────────────────────────────────────


class ReactionEmitter:
    """Sends emoji reactions to specific messages.

    Mirrors OpenClaw's ``src/channels/status-reactions.ts``.
    Used to acknowledge receipt (👍) or signal an error (❌).

    Phase W1: not all channels support reactions — the ``send_fn``
    must be a no-op for channels that don't.
    """

    # Standard reaction codes (mirrors OpenClaw's defaults).
    ACK = "👍"
    ERROR = "❌"
    PROCESSING = "⚙️"
    DONE = "✅"

    def __init__(self, send_fn: Callable[[str, str], Any]) -> None:
        """
        Parameters
        ----------
        send_fn : Callable[[message_id, emoji], Any]
            Channel-specific function to add a reaction to a message.
        """
        self._send_fn = send_fn

    def react(self, message_id: str, emoji: str) -> None:
        """Send a reaction. Silently ignores errors."""
        try:
            self._send_fn(message_id, emoji)
        except Exception as e:  # noqa: BLE001
            _log.debug("reaction: send_fn error: %s", e)

    def ack(self, message_id: str) -> None:
        self.react(message_id, self.ACK)

    def error(self, message_id: str) -> None:
        self.react(message_id, self.ERROR)

    def done(self, message_id: str) -> None:
        self.react(message_id, self.DONE)


__all__ = ["PresenceEmitter", "ReactionEmitter"]
