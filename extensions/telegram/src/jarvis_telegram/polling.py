from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable
    from .client import TelegramClient

_log = logging.getLogger("jarvis.telegram.polling")

class PollingWorker:
    """Long-polling worker for Telegram."""

    def __init__(self, client: TelegramClient, callback: Callable[[dict[str, Any]], None], interval: int = 1):
        self.client = client
        self.callback = callback
        self.interval = interval
        self.is_running = False
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the polling loop in the background."""
        if self.is_running:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._loop())
        _log.info("Telegram polling started")

    async def stop(self) -> None:
        """Stop the polling loop."""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        _log.info("Telegram polling stopped")

    async def _loop(self) -> None:
        offset = 0
        while self.is_running:
            try:
                updates = await self.client.get_updates(offset=offset, timeout=25)
                for update in updates:
                    offset = max(offset, update["update_id"] + 1)
                    # Dispatch update to the plugin callback.
                    # We run this synchronously or fire-and-forget depending on callback signature.
                    # In JARVIS channels_core, listen callbacks are usually sync.
                    try:
                        self.callback(update)
                    except Exception as e:
                        _log.error("Error in Telegram update callback: %s", e)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _log.error("Telegram polling loop error: %s", e)
                await asyncio.sleep(self.interval * 5)
            
            await asyncio.sleep(self.interval)
