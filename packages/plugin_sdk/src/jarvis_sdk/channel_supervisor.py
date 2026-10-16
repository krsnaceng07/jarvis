"""Channel Supervisor — concurrent multi-channel lifecycle management.

Mirrors OpenClaw's ``src/gateway/server-channels.ts`` supervisor pattern.
Starts, supervises, monitors, and gracefully shuts down all configured
channel plugins concurrently.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, cast

_log = logging.getLogger("jarvis_sdk.channel_supervisor")

DEFAULT_CHANNEL_STARTUP_CONCURRENCY = 4


@dataclass
class ChannelAccountState:
    """Runtime state of a single channel or account."""

    channel_id: str
    account_id: str = "default"
    enabled: bool = True
    running: bool = False
    last_error: str | None = None
    reconnect_attempts: int = 0
    task: asyncio.Task[Any] | None = None


class ChannelSupervisor:
    """Supervises all active messaging channels in JARVIS."""

    def __init__(
        self,
        concurrency_limit: int = DEFAULT_CHANNEL_STARTUP_CONCURRENCY,
    ) -> None:
        self.concurrency_limit = concurrency_limit
        self.states: dict[str, ChannelAccountState] = {}
        self._semaphore = asyncio.Semaphore(concurrency_limit)
        self._stop_event = asyncio.Event()

    async def start_channel(
        self,
        channel_id: str,
        channel_reg: dict[str, Any] | Any,
        cfg: dict[str, Any] | None = None,
        on_message: Callable[[Any], Coroutine[Any, Any, None]] | None = None,
    ) -> bool:
        """Start a single channel plugin listener/provider."""
        reg = channel_reg if isinstance(channel_reg, dict) else getattr(channel_reg, "__dict__", {})
        listen_fn = reg.get("listen") or getattr(channel_reg, "listen", None)
        start_account_fn = reg.get("start_account") or getattr(channel_reg, "start_account", None)

        if not callable(listen_fn) and not callable(start_account_fn):
            _log.debug(
                "[%s] channel has no listen or start_account method; skipping startup", channel_id
            )
            return False

        # Check configuration enabled flag
        channels_cfg = (cfg or {}).get("channels", {})
        ch_cfg = channels_cfg.get(channel_id, {})
        if isinstance(ch_cfg, dict) and ch_cfg.get("enabled") is False:
            _log.info("[%s] channel explicitly disabled in config; skipping", channel_id)
            self.states[channel_id] = ChannelAccountState(
                channel_id=channel_id,
                enabled=False,
                running=False,
            )
            return False

        state = self.states.setdefault(channel_id, ChannelAccountState(channel_id=channel_id))
        if state.running:
            _log.debug("[%s] channel is already running", channel_id)
            return True

        async def _run_supervised() -> None:
            async with self._semaphore:
                state.running = True
                state.last_error = None
                _log.info("[%s] channel starting...", channel_id)
                try:
                    if callable(start_account_fn):
                        await cast(Any, start_account_fn)(
                            account=ch_cfg,
                            account_id="default",
                            cfg=cfg or {},
                            on_message=on_message,
                            stop_event=self._stop_event,
                        )
                    elif callable(listen_fn):
                        if on_message is not None:
                            await cast(Any, listen_fn)(on_message)
                        else:
                            await cast(Any, listen_fn)()
                except asyncio.CancelledError:
                    _log.info("[%s] channel listener cancelled", channel_id)
                except Exception as err:
                    state.last_error = str(err)
                    _log.exception("[%s] channel crashed: %s", channel_id, err)
                finally:
                    state.running = False
                    _log.info("[%s] channel stopped", channel_id)

        task = asyncio.create_task(_run_supervised(), name=f"channel_{channel_id}")
        state.task = task
        return True

    async def start_all(
        self,
        channels: dict[str, Any],
        cfg: dict[str, Any] | None = None,
        on_message: Callable[[Any], Coroutine[Any, Any, None]] | None = None,
    ) -> int:
        """Start all configured channels concurrently with bounded concurrency."""
        self._stop_event.clear()
        started_count = 0
        tasks = []
        for channel_id, reg in channels.items():
            tasks.append(self.start_channel(channel_id, reg, cfg, on_message))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in results:
            if res is True:
                started_count += 1
        _log.info("Channel supervisor started %d of %d channels", started_count, len(channels))
        return started_count

    async def stop_channel(self, channel_id: str, timeout_s: float = 5.0) -> None:
        """Stop a specific running channel."""
        state = self.states.get(channel_id)
        if state and state.task and not state.task.done():
            state.task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(state.task), timeout=timeout_s)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            state.running = False

    async def stop_all(self, timeout_s: float = 5.0) -> None:
        """Gracefully stop all supervised channels."""
        self._stop_event.set()
        running_tasks = [s.task for s in self.states.values() if s.task and not s.task.done()]
        if not running_tasks:
            return
        for t in running_tasks:
            t.cancel()
        try:
            await asyncio.wait_for(
                asyncio.gather(*running_tasks, return_exceptions=True),
                timeout=timeout_s,
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass
        for s in self.states.values():
            s.running = False
        _log.info("Channel supervisor stopped all channels")

    def get_status(self, channel_id: str | None = None) -> dict[str, Any]:
        """Return status dictionary for one or all channels."""
        if channel_id is not None:
            st = self.states.get(channel_id)
            if not st:
                return {"channel_id": channel_id, "registered": False, "running": False}
            return {
                "channel_id": st.channel_id,
                "account_id": st.account_id,
                "enabled": st.enabled,
                "running": st.running,
                "last_error": st.last_error,
                "reconnect_attempts": st.reconnect_attempts,
            }
        return {
            cid: {
                "channel_id": s.channel_id,
                "account_id": s.account_id,
                "enabled": s.enabled,
                "running": s.running,
                "last_error": s.last_error,
                "reconnect_attempts": s.reconnect_attempts,
            }
            for cid, s in self.states.items()
        }
