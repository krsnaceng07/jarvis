"""Discord runtime — long-poll loop + process-local singleton.

OpenClaw parity: mirrors ``runtime-setter-api.ts`` (the
TS module exposes a ``setDiscordRuntime`` setter the rest
of the extension calls; the Python port uses a
module-level singleton + setter for the same shape).
"""

from __future__ import annotations

import threading

from .plugin import DiscordPlugin


class DiscordRuntime:
    """The long-poll loop owner. One per process.

    Mirrors the OpenClaw ``DiscordRuntime`` class: holds the
    plugin descriptor + the abort signal the host uses to
    stop the poll loop on shutdown.
    """

    def __init__(self, plugin: DiscordPlugin) -> None:
        self._plugin = plugin
        self._stop = threading.Event()
        self._poll_count = 0

    @property
    def plugin(self) -> DiscordPlugin:
        return self._plugin

    def tick(self) -> int:
        """Run one poll tick. Returns the tick count (1-indexed)."""
        self._poll_count += 1
        return self._poll_count

    def stop(self) -> None:
        self._stop.set()

    def is_stopped(self) -> bool:
        return self._stop.is_set()


# Module-level singleton + setter (matches the TS shape).
_runtime: DiscordRuntime | None = None
_runtime_lock = threading.Lock()


def set_discord_runtime(runtime: DiscordRuntime | None) -> None:
    """Set the process-wide Discord runtime singleton.

    Mirrors OpenClaw's ``setDiscordRuntime`` — the host
    installs the runtime at startup; plugin code reads it
    via ``get_discord_runtime``.
    """
    global _runtime
    with _runtime_lock:
        _runtime = runtime


def get_discord_runtime() -> DiscordRuntime | None:
    """Return the process-wide Discord runtime singleton (or None)."""
    return _runtime
