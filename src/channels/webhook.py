"""Channel webhook — registers gateway routes for inbound channel updates.

Mirrors OpenClaw's ``src/channels/webhook.ts``.

For channels that use push webhooks (rather than long-polling), the
gateway needs to:
  1. Register a ``POST /v1/channels/<id>/inbound`` route.
  2. When a request arrives, decode the body and call the plugin's
     ``on_webhook(body, headers)`` to get a normalized ``InboundMessage``
     dict, then pass it to the ``BindingRouter``.

For channels that use long-polling (like Telegram with ``getUpdates``),
this module starts the polling loop in a daemon thread and wires the
``BindingRouter.make_callback()`` to it.

Usage (in the host, after plugin discovery)::

    wirer = ChannelWirer(catalog, router, gateway)
    wirer.wire_all()
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from jarvis_channels import InboundMessage, derive_webhook_path

from .binding_router import BindingRouter
from .catalog import ChannelCatalog

_log = logging.getLogger("jarvis.channels.webhook")


class ChannelWirer:
    """Wires all registered channel plugins into the gateway and starts listeners.

    Mirrors OpenClaw's channel bootstrapping in
    ``src/channels/plugins/wire.ts``.

    For each channel in the catalog:
    - If it has ``on_webhook``: registers a gateway route at
      ``POST /v1/channels/<id>/inbound``.
    - If it has ``listen``: starts the long-poll loop in a daemon thread,
      wiring the ``BindingRouter.make_callback()`` to the callback param.
    """

    def __init__(
        self,
        catalog: ChannelCatalog,
        router: BindingRouter,
        gateway: Any,  # src.gateway.Gateway — avoid import cycle
    ) -> None:
        self._catalog = catalog
        self._router = router
        self._gateway = gateway
        self._listener_threads: dict[str, threading.Thread] = {}

    def wire_all(self) -> None:
        """Wire every registered channel plugin."""
        for plugin in self._catalog.all():
            self._wire_one(plugin.id)

    def _wire_one(self, channel_id: str) -> None:
        plugin = self._catalog.get(channel_id)
        if plugin is None:
            return

        if plugin.supports_webhook:
            self._register_webhook_route(channel_id, plugin)
        elif plugin.supports_polling:
            self._start_poll_thread(channel_id, plugin)
        else:
            _log.warning(
                "channel_wirer: %s has no listen() or on_webhook(); cannot wire inbound",
                channel_id,
            )

    def _register_webhook_route(self, channel_id: str, plugin: Any) -> None:
        """Register a POST route for a push-webhook channel."""
        path = derive_webhook_path(channel_id)

        def _handler(method: str, _path: str, body: bytes, headers: dict) -> dict:
            if method != "POST":
                return {"error": "method not allowed", "status": 405}
            try:
                raw_body = json.loads(body) if body else {}
            except json.JSONDecodeError:
                return {"error": "invalid JSON body", "status": 400}

            # Call plugin's on_webhook to get the normalized update dict.
            try:
                update = plugin.on_webhook(raw_body, headers)
            except Exception as e:  # noqa: BLE001
                _log.warning("channel_wirer: %s on_webhook error: %s", channel_id, e)
                return {"error": str(e), "status": 500}

            if update is None:
                return {"ok": True}  # plugin chose to ignore this update

            # Convert update dict → InboundMessage.
            msg = InboundMessage(
                channel_id=channel_id,
                conversation_id=str(update.get("conversation_id", "")),
                sender_id=str(update.get("sender_id", "")),
                text=str(update.get("text", "")),
                kind=update.get("kind", "text"),
                raw=update,
                is_owner=bool(update.get("is_owner", False)),
            )
            self._router.handle(msg)
            return {"ok": True}

        try:
            self._gateway.add_route(
                __import__("src.gateway", fromlist=["HttpRoute"]).HttpRoute(
                    path=path,
                    handler=_handler,
                    auth="none",   # channel webhooks use their own token schemes
                    match="exact",
                    owner_id=f"channel:{channel_id}",
                )
            )
            _log.info("channel_wirer: registered webhook route %s for %s", path, channel_id)
        except Exception as e:  # noqa: BLE001
            _log.warning("channel_wirer: could not register route for %s: %s", channel_id, e)

    def _start_poll_thread(self, channel_id: str, plugin: Any) -> None:
        """Start a daemon thread running plugin.listen(callback)."""
        if channel_id in self._listener_threads:
            return  # already started

        callback = self._router.make_callback(channel_id)

        def _run() -> None:
            _log.info("channel_wirer: starting listener for %s", channel_id)
            try:
                plugin.listen(callback)
            except Exception as e:  # noqa: BLE001
                _log.warning("channel_wirer: listener for %s crashed: %s", channel_id, e)

        t = threading.Thread(
            target=_run,
            name=f"jarvis-channel-{channel_id}",
            daemon=True,
        )
        t.start()
        self._listener_threads[channel_id] = t
        _log.info("channel_wirer: poll thread started for %s", channel_id)

    def is_listening(self, channel_id: str) -> bool:
        """Return True if a poll thread is running for ``channel_id``."""
        t = self._listener_threads.get(channel_id)
        return t is not None and t.is_alive()

    def stop_all(self) -> None:
        """Signal all poll threads to stop (joins with 2s timeout each).

        The actual stop is via ``state.stop_flag`` in the channel plugin;
        this method just waits for threads to exit.
        """
        for channel_id, thread in self._listener_threads.items():
            thread.join(timeout=2.0)
            if thread.is_alive():
                _log.debug("channel_wirer: %s listener still alive after stop_all", channel_id)
        self._listener_threads.clear()


__all__ = ["ChannelWirer"]
