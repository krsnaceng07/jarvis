"""packages/net_policy/src/jarvis_net_policy/windows_socket_patch.py

Windows asyncio ProactorBasePipeTransport WinError 10054 resilience patch.

Suppresses harmless ConnectionResetError [WinError 10054] in Python's
asyncio/proactor_events.py line 165 when a remote socket (Telegram long-polling,
Gemini Live WebSocket, or HTTPS server keep-alive) is closed abruptly by the host.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import sys

logger = logging.getLogger("jarvis.net_policy.windows")


def patch_windows_asyncio_connection_lost() -> None:
    """Safely patch Windows asyncio ProactorBasePipeTransport to suppress WinError 10054 on connection_lost.

    On Windows, when a remote peer abruptly resets/closes a TCP connection,
    ProactorEventLoop schedules _call_connection_lost. In Python 3.13 standard library,
    line 165 calls:
        self._sock.shutdown(socket.SHUT_RDWR)
    without catching ConnectionResetError / OSError. This causes unhandled
    ConnectionResetError [WinError 10054] to escape into loop callback handlers.
    Wrapping the shutdown() call ensures clean socket closure without spurious crash traces.
    """
    if sys.platform != "win32":
        return

    try:
        from asyncio import proactor_events

        if getattr(proactor_events, "_PROACTOR_10054_PATCHED", False):
            return

        def _safe_call_connection_lost(self, exc):
            if self._called_connection_lost:
                return
            try:
                self._protocol.connection_lost(exc)
            finally:
                if hasattr(self._sock, "shutdown") and self._sock.fileno() != -1:
                    try:
                        self._sock.shutdown(socket.SHUT_RDWR)
                    except (ConnectionResetError, BrokenPipeError, OSError):
                        pass
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                server = self._server
                if server is not None:
                    server._detach(self)
                    self._server = None
                self._called_connection_lost = True

        proactor_events._ProactorBasePipeTransport._call_connection_lost = _safe_call_connection_lost
        proactor_events._PROACTOR_10054_PATCHED = True
        logger.debug("Windows ProactorEventLoop WinError 10054 resilience patch installed.")
    except Exception as exc:
        logger.debug("Failed installing Windows proactor 10054 patch: %s", exc)


def install_asyncio_resilience_handler(loop: asyncio.AbstractEventLoop | None = None) -> None:
    """Set custom exception handler on asyncio event loop to silence harmless WinError 10054 resets."""
    if sys.platform != "win32":
        return

    if loop is None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

    def _resilient_exception_handler(current_loop, context):
        exc = context.get("exception")
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, ConnectionAbortedError)):
            winerror = getattr(exc, "winerror", None)
            if winerror in (10054, 10053, 10058) or "10054" in str(exc) or "10053" in str(exc):
                # Harmless connection reset from remote host
                return
        msg = context.get("message", "")
        if "10054" in msg or "10053" in msg or "_call_connection_lost" in msg:
            return
        current_loop.default_exception_handler(context)

    loop.set_exception_handler(_resilient_exception_handler)


__all__ = [
    "install_asyncio_resilience_handler",
    "patch_windows_asyncio_connection_lost",
]
