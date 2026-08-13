"""Channel router — resolves inbound messages to channel plugins.

Mirrors OpenClaw's ``src/channels/route-projection.ts`` and the
channel plugin dispatch in ``src/channels/plugins/``.

The ``ChannelRouter`` is the host-side object that:
  1. Holds references to all registered channel plugins.
  2. Routes inbound messages to the right plugin's ``dispatch()`` method.
  3. Provides a ``send()`` facade for agent code to reply without knowing
     which channel is active.

Phase W0.4: minimal contract. The full binding router (Wave 1) will
replace ``dispatch()`` with a full session-aware binding system.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .types import InboundMessage, OutboundMessage, ChannelRouteRef, ConversationRef

_log = logging.getLogger("jarvis_channels.routing")


# ── Channel target ─────────────────────────────────────────────────────


class ChannelTarget:
    """Identifies the destination of an outbound message.

    Mirrors OpenClaw's ``ChannelTarget`` type. Carries the channel id
    and conversation id so the router knows where to send a reply.

    Attributes
    ----------
    channel_id : str
        Channel plugin id (e.g. ``"telegram"``).
    conversation_id : str
        Channel-native conversation id.
    """

    __slots__ = ("channel_id", "conversation_id")

    def __init__(self, channel_id: str, conversation_id: str) -> None:
        self.channel_id = channel_id
        self.conversation_id = conversation_id

    def __repr__(self) -> str:
        return f"ChannelTarget({self.channel_id!r}, {self.conversation_id!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ChannelTarget):
            return NotImplemented
        return self.channel_id == other.channel_id and self.conversation_id == other.conversation_id

    def __hash__(self) -> int:
        return hash((self.channel_id, self.conversation_id))


# ── Channel router ─────────────────────────────────────────────────────


class ChannelRouter:
    """Routes inbound channel messages to the right plugin.

    Mirrors OpenClaw's channel dispatch in ``src/channels/plugins/``.

    Plugins register themselves via ``register(channel_id, plugin)``.
    The gateway calls ``dispatch(message)`` on every inbound event.

    Phase W0.4 shape: plugins are stored as dicts (the raw
    ``api.channel`` registration) until the ``ChannelPlugin`` contract
    is fully fleshed out in Wave 1.
    """

    def __init__(self) -> None:
        # channel_id -> plugin dict (raw api.channel registration for now)
        self._plugins: dict[str, Any] = {}

    def register(self, channel_id: str, plugin: Any) -> None:
        """Register a channel plugin.

        Parameters
        ----------
        channel_id : str
            The plugin's channel id (e.g. ``"telegram"``).
        plugin : Any
            The channel plugin instance or registration dict.
        """
        if channel_id in self._plugins:
            _log.debug("channel_router: replacing %s", channel_id)
        self._plugins[channel_id] = plugin
        _log.debug("channel_router: registered %s", channel_id)

    def register_from_result(self, channel: dict | None) -> None:
        """Register from the ``LoadResult.channel`` slot (single-active).

        The loader's single-active-slot pattern means at most one channel
        is registered here at startup. Wave 1 will support multi-channel.
        """
        if channel is None:
            return
        cid = channel.get("id", "")
        if not cid:
            _log.warning("channel_router: channel registration missing 'id'; ignoring")
            return
        self.register(cid, channel)

    def is_registered(self, channel_id: str) -> bool:
        """Return True if a plugin is registered for ``channel_id``."""
        return channel_id in self._plugins

    def get(self, channel_id: str) -> Any | None:
        """Return the plugin for ``channel_id``, or None."""
        return self._plugins.get(channel_id)

    def registered_ids(self) -> list[str]:
        """Return the ids of all registered channel plugins."""
        return list(self._plugins.keys())

    async def dispatch(self, message: InboundMessage) -> bool:
        """Route an inbound message to the correct channel plugin.

        Returns True if a plugin handled the message, False if no plugin
        is registered for the message's channel.

        Phase W0.4: if the plugin has a ``dispatch`` method, calls it.
        Otherwise logs a warning and returns False.
        """
        plugin = self._plugins.get(message.channel_id)
        if plugin is None:
            _log.warning(
                "channel_router: no plugin for channel %r; dropping message",
                message.channel_id,
            )
            return False

        dispatch_fn = getattr(plugin, "dispatch", None)
        if dispatch_fn is None:
            _log.debug(
                "channel_router: plugin %r has no dispatch(); accepting silently",
                message.channel_id,
            )
            return True

        try:
            await dispatch_fn(message)
            return True
        except Exception as e:  # noqa: BLE001
            _log.warning("channel_router: dispatch to %r failed: %s", message.channel_id, e)
            return False

    async def send(self, message: OutboundMessage) -> bool:
        """Send an outbound message through the target channel plugin.

        Returns True on success, False if the channel is not registered
        or the plugin's ``send()`` call fails.
        """
        plugin = self._plugins.get(message.channel_id)
        if plugin is None:
            _log.warning(
                "channel_router: cannot send to channel %r; not registered",
                message.channel_id,
            )
            return False

        send_fn = getattr(plugin, "send", None)
        if send_fn is None:
            _log.debug(
                "channel_router: plugin %r has no send(); dropping message",
                message.channel_id,
            )
            return False

        try:
            await send_fn(message)
            return True
        except Exception as e:  # noqa: BLE001
            _log.warning("channel_router: send to %r failed: %s", message.channel_id, e)
            return False


__all__ = [
    "ChannelTarget",
    "ChannelRouter",
    "format_conversation_target",
    "resolve_conversation_delivery_target",
    "route_from_conversation_ref",
    "route_from_binding_record",
    "route_to_delivery_fields",
]


# ── Route projection helpers ───────────────────────────────────────────


def format_conversation_target(router: ChannelRouter, params: dict) -> Optional[str]:
    """Formats a conversation id into a deliverable target."""
    channel = params.get("channel")
    conversation_id = params.get("conversation_id")
    parent_conversation_id = params.get("parent_conversation_id")

    if not channel or not conversation_id:
        return None

    plugin = router.get(channel)
    if plugin and hasattr(plugin, "resolve_delivery_target"):
        target = plugin.resolve_delivery_target(
            {
                "conversation_id": conversation_id,
                "parent_conversation_id": parent_conversation_id,
            }
        )
        if target and target.get("to"):
            return target["to"].strip()

    return f"channel:{conversation_id}"


def resolve_conversation_delivery_target(router: ChannelRouter, params: dict) -> dict:
    """Resolves a channel conversation into target/thread fields for delivery routing."""
    channel = params.get("channel")
    conversation_id = params.get("conversation_id")
    parent_conversation_id = params.get("parent_conversation_id")

    if channel and conversation_id:
        plugin = router.get(channel)
        if plugin and hasattr(plugin, "resolve_delivery_target"):
            target = plugin.resolve_delivery_target(
                {
                    "conversation_id": conversation_id,
                    "parent_conversation_id": parent_conversation_id,
                }
            )
            if target:
                res = {}
                if target.get("to"):
                    res["to"] = target["to"].strip()
                if target.get("thread_id"):
                    res["thread_id"] = str(target["thread_id"]).strip()
                return res

    to = format_conversation_target(router, params)
    return {"to": to} if to else {}


def route_from_conversation_ref(
    router: ChannelRouter, conversation: Optional["ConversationRef"]
) -> Optional["ChannelRouteRef"]:
    """Converts a persisted conversation reference into a channel route."""
    if not conversation:
        return None

    from .types import ChannelRouteRef, ChannelRouteTarget, ChannelRouteThread

    target_fields = resolve_conversation_delivery_target(
        router,
        {
            "channel": conversation.channel,
            "conversation_id": conversation.conversation_id,
            "parent_conversation_id": conversation.parent_conversation_id,
        },
    )

    thread = None
    if "thread_id" in target_fields:
        thread = ChannelRouteThread(id=target_fields["thread_id"], source="target")

    target = None
    if "to" in target_fields:
        target = ChannelRouteTarget(to=target_fields["to"])

    return ChannelRouteRef(
        channel=conversation.channel,
        account_id=conversation.account_id,
        target=target,
        thread=thread,
    )


def route_from_binding_record(
    router: ChannelRouter, binding: Optional[dict]
) -> Optional["ChannelRouteRef"]:
    """Extracts a channel route from a session binding record."""
    if not binding:
        return None
    return route_from_conversation_ref(router, binding.get("conversation"))


def route_to_delivery_fields(route: Optional["ChannelRouteRef"]) -> dict:
    """Projects route fields used by older session and delivery callers."""
    if not route:
        return {}

    fields = {}
    if route.channel:
        fields["channel"] = route.channel
    if route.target and route.target.to:
        fields["to"] = route.target.to
    if route.account_id:
        fields["account_id"] = route.account_id
    if route.thread and route.thread.id is not None:
        fields["thread_id"] = route.thread.id

    return fields
