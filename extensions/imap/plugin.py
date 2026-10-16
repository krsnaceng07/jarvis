"""IMAP extension entry point for JARVIS."""

from __future__ import annotations

import logging
from typing import Any

from .src.config import resolve_imap_config
from .src.state import create_imap_state
from .src.watcher import ImapAccountWatcher

logger = logging.getLogger("jarvis.extensions.imap")


class ImapExtension:
    id = "imap"
    name = "IMAP email trigger"
    description = "Dispatch authenticated incoming IMAP email to isolated agent sessions."

    def __init__(self) -> None:
        self.watchers: list[ImapAccountWatcher] = []

    def register(self, api: Any) -> None:
        if getattr(api, "registration_mode", "full") != "full":
            return

        def start_service(context: Any) -> None:
            config = resolve_imap_config(getattr(api, "plugin_config", {}))
            if not config.accounts:
                logger.warning(
                    "imap: no accounts configured; add plugins.entries.imap.config.accounts"
                )
                return

            state = create_imap_state(getattr(api, "runtime", None))
            self.watchers = [
                ImapAccountWatcher(
                    account_id=acc_id,
                    account=acc_cfg,
                    runtime=getattr(api, "runtime", None),
                    state=state,
                    context=context,
                )
                for acc_id, acc_cfg in config.accounts.items()
            ]
            for watcher in self.watchers:
                watcher.start()

        async def stop_service() -> None:
            active = self.watchers
            self.watchers = []
            for watcher in active:
                await watcher.stop()

        if hasattr(api, "register_service"):
            api.register_service(
                {
                    "id": "imap-watch",
                    "start": start_service,
                    "stop": stop_service,
                }
            )


plugin = ImapExtension()
entry = plugin

__all__ = ["ImapExtension", "plugin", "entry"]
