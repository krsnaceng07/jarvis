"""Channel plugin catalog — discovers channel plugins from LoadResult.

Mirrors OpenClaw's ``src/channels/plugins/catalog.ts``.

The ``ChannelCatalog`` is populated once at startup from the
``LoadResult`` produced by the plugin loader. It holds a typed view
of every channel plugin that registered itself via
``api.register_channel({...})``.

A channel plugin registration dict has the shape::

    {
        "id": "telegram",
        "send": <callable>,           # (target, message) -> dict
        "listen": <callable>,         # (callback) -> None  (long-poll)
        "on_webhook": <callable|None>,# (body, headers) -> dict (optional)
        "config_schema": {...},       # JSON Schema (optional)
    }

The ``ChannelPlugin`` dataclass wraps this dict into a typed interface.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_log = logging.getLogger("jarvis.channels.catalog")


# ── Channel plugin dataclass ───────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChannelPlugin:
    """Typed wrapper around a channel plugin registration dict.

    Mirrors OpenClaw's ``ChannelPlugin`` interface from
    ``src/channels/plugins/types.ts``.

    Attributes
    ----------
    id : str
        Channel plugin id (e.g. ``"telegram"``).
    send : Callable
        ``send(target, message) -> dict`` — send a reply.
    listen : Callable | None
        ``listen(callback) -> None`` — long-poll loop (optional).
    on_webhook : Callable | None
        ``on_webhook(body, headers) -> dict`` — handle inbound HTTP
        webhook (optional; used instead of ``listen`` for push-based
        channels like Discord bot webhooks).
    config_schema : dict
        JSON Schema describing required channel configuration.
    raw : dict
        The original registration dict (for channels that need it).
    """

    id: str
    send: Callable[..., Any]
    listen: Callable[..., Any] | None = None
    on_webhook: Callable[..., Any] | None = None
    config_schema: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def supports_polling(self) -> bool:
        """True if the channel uses long-polling (``listen`` is set)."""
        return self.listen is not None

    @property
    def supports_webhook(self) -> bool:
        """True if the channel uses push webhooks (``on_webhook`` is set)."""
        return self.on_webhook is not None


# ── Catalog ────────────────────────────────────────────────────────────


class ChannelCatalog:
    """Holds all registered channel plugins.

    Mirrors OpenClaw's ``ChannelPluginCatalog`` from
    ``src/channels/plugins/catalog.ts``.

    Created once at startup by the host; populated from ``LoadResult``.
    The gateway and channel router use the catalog to look up plugins
    by channel id.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, ChannelPlugin] = {}

    def register(self, plugin: ChannelPlugin) -> None:
        """Register a channel plugin."""
        if plugin.id in self._plugins:
            _log.debug("channel_catalog: replacing %s", plugin.id)
        self._plugins[plugin.id] = plugin
        _log.info("channel_catalog: registered %s", plugin.id)

    def register_raw(self, raw: dict[str, Any] | None) -> None:
        """Register from a raw ``api.register_channel({...})`` dict.

        Mirrors the ``LoadResult.channel`` single-active-slot pattern.
        Silently skips ``None``.
        """
        if raw is None:
            return
        cid = raw.get("id", "")
        if not cid:
            _log.warning("channel_catalog: registration missing 'id'; skipping")
            return
        send_fn = raw.get("send")
        if not callable(send_fn):
            _log.warning("channel_catalog: %s missing callable 'send'; skipping", cid)
            return
        listen_fn = raw.get("listen")
        webhook_fn = raw.get("on_webhook")
        plugin = ChannelPlugin(
            id=cid,
            send=send_fn,
            listen=listen_fn if callable(listen_fn) else None,
            on_webhook=webhook_fn if callable(webhook_fn) else None,
            config_schema=raw.get("config_schema") or {},
            raw=raw,
        )
        self.register(plugin)

    def get(self, channel_id: str) -> ChannelPlugin | None:
        """Return the plugin for ``channel_id``, or None."""
        return self._plugins.get(channel_id)

    def all(self) -> list[ChannelPlugin]:
        """Return all registered channel plugins."""
        return list(self._plugins.values())

    def ids(self) -> list[str]:
        """Return the ids of all registered channels."""
        return list(self._plugins.keys())

    def is_registered(self, channel_id: str) -> bool:
        return channel_id in self._plugins

    def __len__(self) -> int:
        return len(self._plugins)


__all__ = ["ChannelCatalog", "ChannelPlugin"]
