"""Channel typing indicator lifecycle — keepalive loop, circuit breaker, safety TTL.

Mirrors OpenClaw's:
- ``src/channels/typing.ts``
- ``src/channels/typing-lifecycle.ts``
- ``src/channels/typing-start-guard.ts``

Features:
- Periodic keepalive loop (~3s interval) to refresh expiring platform indicators.
- Concurrency start guard: ensures overlapping ticks do not trigger concurrent starts.
- Consecutive failure circuit breaker: stops keepalive if platform rejects 2 consecutive signals.
- Safety TTL timer (default 60s): auto-stops typing if turn runs excessively long.
- Fully async and safe from dangling tasks.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable

_log = logging.getLogger("jarvis_channels.typing")

DEFAULT_KEEPALIVE_INTERVAL_S = 3.0
DEFAULT_MAX_CONSECUTIVE_FAILURES = 2
DEFAULT_SAFETY_TTL_S = 60.0


class TypingStartGuard:
    """Gates typing indicator starts with concurrency protection and circuit breaker."""

    def __init__(
        self,
        max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
        on_start_error: Callable[[Exception], None] | None = None,
        on_trip: Callable[[], None] | None = None,
    ) -> None:
        self.max_consecutive_failures = max_consecutive_failures
        self.on_start_error = on_start_error
        self.on_trip = on_trip
        self._consecutive_failures = 0
        self._tripped = False
        self._sealed = False
        self._lock = asyncio.Lock()

    def is_tripped(self) -> bool:
        return self._tripped

    def is_sealed(self) -> bool:
        return self._sealed

    def seal(self) -> None:
        self._sealed = True

    def reset(self) -> None:
        self._consecutive_failures = 0
        self._tripped = False
        self._sealed = False

    async def run(self, fn: Callable[[], Awaitable[None]]) -> None:
        """Execute a start signal if not sealed or tripped."""
        if self._sealed or self._tripped:
            return

        async with self._lock:
            if self._sealed or self._tripped:
                return
            try:
                await fn()
                self._consecutive_failures = 0
            except Exception as err:
                self._consecutive_failures += 1
                if self.on_start_error:
                    self.on_start_error(err)
                _log.debug(
                    "Typing start signal failed (%d/%d): %s",
                    self._consecutive_failures,
                    self.max_consecutive_failures,
                    err,
                )
                if self._consecutive_failures >= self.max_consecutive_failures:
                    self._tripped = True
                    _log.warning(
                        "Typing start guard tripped after %d consecutive failures",
                        self._consecutive_failures,
                    )
                    if self.on_trip:
                        self.on_trip()


class TypingKeepaliveLoop:
    """Runs a periodic keepalive loop to keep channel typing active."""

    def __init__(
        self,
        interval_s: float,
        on_tick: Callable[[], Awaitable[None]],
    ) -> None:
        self.interval_s = interval_s
        self.on_tick = on_tick
        self._task: asyncio.Task | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True

        async def _loop() -> None:
            while self._running:
                try:
                    await asyncio.sleep(self.interval_s)
                    if self._running:
                        await self.on_tick()
                except asyncio.CancelledError:
                    break
                except Exception as err:
                    _log.debug("Typing keepalive tick error: %s", err)

        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(_loop())
        except RuntimeError:
            pass

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None


@dataclass(frozen=True, slots=True)
class TypingCallbacks:
    """Callbacks exposing typing indicator lifecycle to turn dispatchers."""

    on_reply_start: Callable[[], Awaitable[None]]
    on_idle: Callable[[], None] | None = None
    on_cleanup: Callable[[], None] | None = None


def create_typing_callbacks(
    start: Callable[[], Awaitable[None]],
    stop: Callable[[], Awaitable[None]] | None = None,
    keepalive_interval_s: float = DEFAULT_KEEPALIVE_INTERVAL_S,
    max_consecutive_failures: int = DEFAULT_MAX_CONSECUTIVE_FAILURES,
    safety_ttl_s: float = DEFAULT_SAFETY_TTL_S,
    on_start_error: Callable[[Exception], None] | None = None,
    on_stop_error: Callable[[Exception], None] | None = None,
) -> TypingCallbacks:
    """Create OpenClaw-parity TypingCallbacks for channel turn execution."""
    closed = False
    ttl_task: asyncio.Task | None = None

    start_guard = TypingStartGuard(
        max_consecutive_failures=max_consecutive_failures,
        on_start_error=on_start_error,
        on_trip=lambda: keepalive_loop.stop(),
    )

    async def _fire_start() -> None:
        await start_guard.run(start)

    keepalive_loop = TypingKeepaliveLoop(
        interval_s=keepalive_interval_s,
        on_tick=_fire_start,
    )

    def _clear_ttl() -> None:
        nonlocal ttl_task
        if ttl_task and not ttl_task.done():
            ttl_task.cancel()
            ttl_task = None

    def _start_ttl() -> None:
        nonlocal ttl_task
        if safety_ttl_s <= 0:
            return
        _clear_ttl()

        async def _ttl() -> None:
            try:
                await asyncio.sleep(safety_ttl_s)
                if not closed:
                    _log.warning(
                        "[typing] Safety TTL exceeded (%.1fs), auto-stopping indicator",
                        safety_ttl_s,
                    )
                    _fire_stop_sync()
            except asyncio.CancelledError:
                pass

        try:
            loop = asyncio.get_running_loop()
            ttl_task = loop.create_task(_ttl())
        except RuntimeError:
            pass

    async def _on_reply_start() -> None:
        nonlocal closed
        if closed:
            return
        start_guard.reset()
        _clear_ttl()
        await _fire_start()
        if not closed and not start_guard.is_tripped():
            keepalive_loop.start()
            _start_ttl()

    def _fire_stop_sync() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        start_guard.seal()
        keepalive_loop.stop()
        _clear_ttl()

        if stop:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_run_stop())
            except RuntimeError:
                pass

    async def _run_stop() -> None:
        if stop:
            try:
                await stop()
            except Exception as err:
                if on_stop_error:
                    on_stop_error(err)
                elif on_start_error:
                    on_start_error(err)
                _log.debug("Typing stop error: %s", err)

    return TypingCallbacks(
        on_reply_start=_on_reply_start,
        on_idle=_fire_stop_sync,
        on_cleanup=_fire_stop_sync,
    )


class TypingIndicator:
    """Compatible TypingIndicator for existing JARVIS channels."""

    def __init__(
        self,
        send_typing_fn: Callable[[], Awaitable[None]] | None = None,
        interval_s: float = DEFAULT_KEEPALIVE_INTERVAL_S,
    ) -> None:
        self._send_typing_fn = send_typing_fn
        self._interval_s = interval_s
        self._callbacks: TypingCallbacks | None = None
        self._is_active = False

        if self._send_typing_fn:
            self._callbacks = create_typing_callbacks(
                start=self._send_typing_fn,
                keepalive_interval_s=self._interval_s,
            )

    @property
    def is_active(self) -> bool:
        return self._is_active

    async def start(self) -> None:
        """Start typing indicator with keepalive loop."""
        if self._is_active or not self._callbacks:
            return
        self._is_active = True
        await self._callbacks.on_reply_start()

    async def stop(self) -> None:
        """Stop typing indicator."""
        if not self._is_active:
            return
        self._is_active = False
        if self._callbacks and self._callbacks.on_cleanup:
            self._callbacks.on_cleanup()


__all__ = [
    "DEFAULT_KEEPALIVE_INTERVAL_S",
    "DEFAULT_MAX_CONSECUTIVE_FAILURES",
    "DEFAULT_SAFETY_TTL_S",
    "TypingCallbacks",
    "TypingIndicator",
    "TypingKeepaliveLoop",
    "TypingStartGuard",
    "create_typing_callbacks",
]
