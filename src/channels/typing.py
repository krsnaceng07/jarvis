"""Typing indicator manager — mirrors OpenClaw ``src/channels/typing.ts``."""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable

_log = logging.getLogger("jarvis.channels.typing")


class TypingIndicator:
    """Manages channel typing indicator lifecycle and debouncing."""

    def __init__(
        self,
        send_typing_fn: Callable[[], Awaitable[None]] | None = None,
        interval_s: float = 4.0,
    ) -> None:
        self._send_typing_fn = send_typing_fn
        self._interval_s = interval_s
        self._task: asyncio.Task | None = None
        self._is_active = False

    @property
    def is_active(self) -> bool:
        return self._is_active

    async def start(self) -> None:
        """Start periodic typing signals if not already active."""
        if self._is_active or not self._send_typing_fn:
            return

        self._is_active = True

        async def _loop() -> None:
            while self._is_active:
                try:
                    if self._send_typing_fn:
                        await self._send_typing_fn()
                except Exception as e:
                    _log.debug("Typing signal failed: %s", e)
                await asyncio.sleep(self._interval_s)

        self._task = asyncio.create_task(_loop())

    async def stop(self) -> None:
        """Stop periodic typing signals."""
        if not self._is_active:
            return
        self._is_active = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


__all__ = ["TypingIndicator"]
