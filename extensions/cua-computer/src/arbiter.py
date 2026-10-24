"""extensions/cua-computer/src/arbiter.py

Input Lease Arbiter managing exclusive access to physical input devices.
Coordinates state transitions, action coalescing, idle auto-release,
runaway hard-cap enforcement, and instantaneous user takeover abortion.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import time
from typing import Any, AsyncIterator, Callable, Optional
import uuid

from jarvis_sdk.input_backend import ComputerFailureCode, InputBackend, LeaseState

from .win.watcher import LowLevelInputWatcher

logger = logging.getLogger(__name__)


class UserTakeoverException(Exception):
    """Raised when the user moves physical mouse or presses keyboard during active lease."""

    def __init__(self, message: str = "User took over physical input", details: dict | None = None) -> None:
        super().__init__(message)
        self.code = ComputerFailureCode.USER_TOOK_OVER
        self.details = details or {}


class PanicStopException(Exception):
    """Raised when user presses panic hotkey (Pause/Break or Ctrl+Alt+Esc)."""

    def __init__(self, message: str = "Emergency panic stop triggered") -> None:
        super().__init__(message)
        self.code = ComputerFailureCode.PANIC_STOP


class LeaseBusyException(Exception):
    """Raised when lease cannot be acquired because another session holds it or in cooldown."""

    def __init__(self, message: str = "Input lease is busy or in cooldown") -> None:
        super().__init__(message)
        self.code = ComputerFailureCode.LEASE_BUSY


class InputLeaseArbiter:
    """Manages exclusive time-bounded input leases for JARVIS computer use."""

    def __init__(
        self,
        backend: InputBackend,
        watcher: Optional[LowLevelInputWatcher] = None,
        coalesce_window_s: float = 1.5,
        idle_timeout_s: float = 3.0,
        max_duration_s: float = 120.0,
        abort_cooldown_s: float = 2.0,
        on_lease_event: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self.backend = backend
        self.watcher = watcher
        self.coalesce_window_s = coalesce_window_s
        self.idle_timeout_s = idle_timeout_s
        self.max_duration_s = max_duration_s
        self.abort_cooldown_s = abort_cooldown_s
        self.on_lease_event = on_lease_event

        self._state: LeaseState = LeaseState.IDLE
        self._current_lease_id: str | None = None
        self._lease_start_time: float = 0.0
        self._last_action_time: float = 0.0
        self._last_abort_time: float = 0.0
        self._action_count: int = 0
        self._abort_reason: str | None = None

        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

        # Connect watcher callbacks if watcher provided
        if self.watcher:
            self.watcher.on_human_input = self._handle_human_input
            self.watcher.on_panic = self._handle_panic

    @property
    def state(self) -> LeaseState:
        return self._state

    @property
    def current_lease_id(self) -> str | None:
        return self._current_lease_id

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.on_lease_event:
            try:
                self.on_lease_event(event_type, data)
            except Exception as e:
                logger.debug("Lease event emission failed: %s", e)

    def _handle_human_input(self, source: str, event_data: dict[str, Any]) -> None:
        """Callback from low-level watcher when physical mouse/keyboard activity is detected."""
        if self._state in (LeaseState.ARMING, LeaseState.ACTIVE):
            logger.warning("Human takeover detected (%s): %s", source, event_data)
            self._abort(ComputerFailureCode.USER_TOOK_OVER, f"User moved physical {source}")

    def _handle_panic(self) -> None:
        """Callback from low-level watcher on global panic key."""
        logger.warning("Panic stop key triggered!")
        self._abort(ComputerFailureCode.PANIC_STOP, "Panic key pressed")

    def _abort(self, code: ComputerFailureCode, reason: str) -> None:
        """Immediate abort transition."""
        self._state = LeaseState.ABORTED
        self._abort_reason = reason
        self._last_abort_time = time.time()

        if self.watcher:
            self.watcher.disarm()

        # Cancel any pending idle timeout release
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()
            self._idle_task = None

        self._emit(
            "event.computer.lease.aborted",
            {
                "lease_id": self._current_lease_id,
                "reason": reason,
                "code": code.value,
                "timestamp": self._last_abort_time,
            },
        )

    async def _idle_watchdog(self, lease_id: str) -> None:
        """Monitors idle time and automatically releases lease when cooldown expires."""
        try:
            while True:
                await asyncio.sleep(0.2)
                async with self._lock:
                    if self._current_lease_id != lease_id or self._state != LeaseState.ACTIVE:
                        break

                    now = time.time()
                    # Check runaway hard-cap
                    if (now - self._lease_start_time) >= self.max_duration_s:
                        logger.warning("Lease %s reached max duration %ss, releasing", lease_id, self.max_duration_s)
                        await self._release_locked(reason="max_duration_reached")
                        break

                    # Check idle timeout
                    if (now - self._last_action_time) >= self.idle_timeout_s:
                        logger.info("Lease %s idle for %ss, releasing", lease_id, self.idle_timeout_s)
                        await self._release_locked(reason="idle_timeout")
                        break
        except asyncio.CancelledError:
            pass

    async def _release_locked(self, reason: str = "normal") -> None:
        """Transition from ACTIVE to RELEASING to IDLE and restore cursor."""
        if self._state not in (LeaseState.ACTIVE, LeaseState.ARMING):
            return

        self._state = LeaseState.RELEASING
        self._emit(
            "event.computer.lease.releasing",
            {"lease_id": self._current_lease_id, "reason": reason},
        )

        if self.watcher:
            self.watcher.disarm()

        # Restore user's original hardware cursor position
        try:
            self.backend.restore_cursor_pos()
        except Exception as e:
            logger.debug("Failed restoring cursor pos: %s", e)

        # Brief settle time for overlay animation fade out
        await asyncio.sleep(0.08)

        self._state = LeaseState.IDLE
        released_lease = self._current_lease_id
        duration = time.time() - self._lease_start_time
        self._current_lease_id = None

        self._emit(
            "event.computer.lease.idle",
            {
                "lease_id": released_lease,
                "duration_s": duration,
                "actions_count": self._action_count,
            },
        )

    @asynccontextmanager
    async def acquire_lease(
        self, session_id: str, action_name: str
    ) -> AsyncIterator[str]:
        """Async context manager to acquire and hold an input lease for an action."""
        async with self._lock:
            now = time.time()
            # 1. Check cooldown after user abort
            if (now - self._last_abort_time) < self.abort_cooldown_s:
                self._state = LeaseState.DENIED
                self._emit("event.computer.lease.denied", {"reason": "cooldown_active"})
                raise LeaseBusyException(
                    f"User takeover cooldown active for {self.abort_cooldown_s - (now - self._last_abort_time):.1f}s"
                )

            # 2. Check if active lease can be coalesced
            if self._state == LeaseState.ACTIVE and self._current_lease_id is not None:
                # Coalesce into existing lease
                self._last_action_time = now
                self._action_count += 1
                lease_id = self._current_lease_id
            else:
                # 3. New Lease Acquisition
                lease_id = str(uuid.uuid4())[:8]
                self._current_lease_id = lease_id
                self._lease_start_time = now
                self._last_action_time = now
                self._action_count = 1
                self._abort_reason = None

                # ARMING
                self._state = LeaseState.ARMING
                self._emit(
                    "event.computer.lease.arming",
                    {"lease_id": lease_id, "session_id": session_id, "action": action_name},
                )

                # Save original user cursor position before synthetic movement
                self.backend.save_cursor_pos()

                if self.watcher:
                    self.watcher.arm()

                # ACTIVE
                self._state = LeaseState.ACTIVE
                self._emit(
                    "event.computer.lease.active",
                    {"lease_id": lease_id, "session_id": session_id, "action": action_name},
                )

            # Ensure idle watchdog is running
            if self._idle_task is None or self._idle_task.done():
                self._idle_task = asyncio.create_task(self._idle_watchdog(lease_id))

        try:
            # Yield control to execute the action
            yield lease_id

            # Check if an abort occurred during action execution
            if self._state == LeaseState.ABORTED:
                if self._abort_reason and "panic" in self._abort_reason.lower():
                    raise PanicStopException(self._abort_reason)
                raise UserTakeoverException(self._abort_reason or "User took over physical input")

            self._last_action_time = time.time()

        except (UserTakeoverException, PanicStopException):
            raise
        except Exception as e:
            logger.debug("Exception in action block under lease %s: %s", lease_id, e)
            raise


__all__ = [
    "InputLeaseArbiter",
    "LeaseBusyException",
    "PanicStopException",
    "UserTakeoverException",
]
