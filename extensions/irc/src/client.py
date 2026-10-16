"""Async IRC Client supporting channel join, PRIVMSG, and PING response."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from .protocol import format_irc_line, parse_irc_line, strip_irc_formatting

logger = logging.getLogger("jarvis.extensions.irc")


class IrcClient:
    """Async IRC protocol client."""

    def __init__(
        self,
        host: str,
        port: int = 6667,
        nick: str = "jarvis_bot",
        password: str | None = None,
        channels: list[str] | None = None,
        on_message: Callable[[str, str, str], Any] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.nick = nick
        self.password = password
        self.channels = channels or []
        self.on_message = on_message

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        """Connect to IRC server and start read loop."""
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._running = True

        if self.password:
            self._send(format_irc_line("PASS", self.password))
        self._send(format_irc_line("NICK", self.nick))
        self._send(format_irc_line("USER", self.nick, "0", "*", trailing=self.nick))

        self._task = asyncio.create_task(self._listen_loop())

    async def disconnect(self) -> None:
        """Disconnect cleanly from IRC server."""
        self._running = False
        if self._writer:
            try:
                self._send(format_irc_line("QUIT", trailing="Jarvis shutting down"))
                await self._writer.drain()
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def send_privmsg(self, target: str, message: str) -> None:
        """Send PRIVMSG to channel or nickname."""
        self._send(format_irc_line("PRIVMSG", target, trailing=strip_irc_formatting(message)))

    def _send(self, raw_line: str) -> None:
        if self._writer and not self._writer.is_closing():
            self._writer.write(raw_line.encode("utf-8", errors="replace"))

    async def _listen_loop(self) -> None:
        while self._running and self._reader:
            line_bytes = await self._reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="replace")
            msg = parse_irc_line(line)
            if not msg:
                continue

            # Handle PING
            if msg.command == "PING":
                self._send(format_irc_line("PONG", trailing=msg.trailing or ""))
                continue

            # Handle 001 (RPL_WELCOME) -> Join channels
            if msg.command in ("001", "RPL_WELCOME"):
                for ch in self.channels:
                    self._send(format_irc_line("JOIN", ch))

            # Handle PRIVMSG
            if msg.command == "PRIVMSG" and msg.params:
                target = msg.params[0]
                text = msg.trailing or ""
                sender = msg.nick or "unknown"
                if self.on_message:
                    res = self.on_message(target, sender, text)
                    if hasattr(res, "__await__"):
                        await res
