"""Slash-command router for the JARVIS desktop host.

Mirrors OpenClaw's command-routing flow. When the operator issues a
message starting with ``/``, the host parses the command name, looks
up the plugin-registered handler from ``_PLUGIN_COMMANDS`` (set by
``_load_plugins`` at startup), invokes ``handler(ctx)`` with a
``PluginCommandContext``, and returns the ``reply_text`` instead of
forwarding to the LLM.

Free-text (no leading ``/``) falls through to the LLM as before.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from jarvis_sdk import CommandDecl, PluginCommandContext, PluginCommandResult

if TYPE_CHECKING:
    from .ui import JarvisUI


class CommandRouter:
    """Routes ``/slash-commands`` to plugin-registered handlers.

    Mirrors the routing surface in OpenClaw's command dispatcher. The
    router is constructed once at startup with the list of
    ``CommandDecl`` produced by ``_load_plugins``.

    Usage::

        router = CommandRouter(_PLUGIN_COMMANDS, ui=self.ui)
        result = await router.dispatch("/reminders list")
        if result is not None:
            self.ui.write_log(result.reply_text)
            return  # skip the LLM
    """

    def __init__(
        self,
        commands: list[CommandDecl],
        *,
        ui: "JarvisUI | None" = None,
        config: dict | None = None,
    ) -> None:
        # Index by name for O(1) lookup. Last-write-wins on collisions.
        self._by_name: dict[str, CommandDecl] = {c.name: c for c in commands}
        self._ui = ui
        self._config = config or {}

    def names(self) -> list[str]:
        """Return the sorted list of registered command names."""
        return sorted(self._by_name.keys())

    def lookup(self, name: str) -> CommandDecl | None:
        """Return the ``CommandDecl`` for ``name`` (without leading ``/``)."""
        return self._by_name.get(name.lstrip("/"))

    async def dispatch(self, text: str) -> PluginCommandResult | None:
        """Route ``text`` if it starts with ``/``.

        Returns ``None`` if the text isn't a slash command (so the
        caller can fall through to the LLM). Returns a
        ``PluginCommandResult`` if a command was found and executed.
        """
        stripped = text.strip()
        if not stripped.startswith("/"):
            return None

        # Parse: /<name> [args...]
        head, _, tail = stripped[1:].partition(" ")
        name = head.strip()
        if not name:
            return PluginCommandResult(reply_text="Empty command name.")

        cmd = self.lookup(name)
        if cmd is None:
            return PluginCommandResult(
                reply_text=f"Unknown command: /{name}. Try: {', '.join('/' + n for n in self.names())}",
                suppress_reply=False,
            )

        ctx = PluginCommandContext(
            sender_id="operator",
            channel="live",
            is_authorized_sender=True,
            sender_is_owner=cmd.expose_sender_is_owner,
            args=tail.strip() or None,
            command_body=stripped,
            config=self._config,
        )
        result = cmd.handler(ctx)
        if asyncio.iscoroutine(result):
            result = await result
        # Best-effort UI feedback.
        if self._ui is not None and result.reply_text:
            with __import__("contextlib").suppress(Exception):
                self._ui.write_log(f"[/{name}] {result.reply_text}")
        return result


__all__ = ["CommandRouter"]
