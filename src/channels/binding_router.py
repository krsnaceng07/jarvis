"""Channel binding router — maps inbound messages to agent sessions.

Mirrors OpenClaw's ``src/channels/binding-router.ts`` +
``src/channels/session-dispatch.ts``.

The ``BindingRouter`` is the host-level orchestrator that:
  1. Receives an inbound message from a channel plugin (via webhook or
     long-poll callback).
  2. Checks the allowlist — drops the message if the sender is not allowed.
  3. Gets or creates a ``ChannelSession`` from the ``BindingRegistry``.
  4. Dispatches the message to the agent session runner.
  5. Sends the agent reply back through the channel's ``send()`` method.

Phase W1: the agent dispatch calls a provided ``agent_fn`` callback
(sync). The streaming / async variant lands in Wave 2.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from jarvis_channels import (
    BindingRegistry,
    PresenceEmitter,
    is_allowed,
    split_reply,
)
from jarvis_channels.types import InboundMessage
from jarvis_channels.location import format_inbound_location
from jarvis_channels.router import resolve_agent, derive_session_key
from jarvis_channels.allowlist import AllowlistPolicy
from jarvis_config_core import JarvisConfig
from src.sessions.session_store import SessionStore

from .catalog import ChannelCatalog

_log = logging.getLogger("jarvis.channels.binding_router")


# ── Types ──────────────────────────────────────────────────────────────

# Agent dispatch fn: (session_key, message_text) -> reply_text | None
AgentDispatchFn = Callable[[str, str], str | None]


# ── Binding router ─────────────────────────────────────────────────────


class BindingRouter:
    """Routes inbound channel messages through allowlist → session → agent → reply.

    Mirrors OpenClaw's ``ChannelBindingRouter`` from
    ``src/channels/binding-router.ts``.

    The host creates one ``BindingRouter`` at startup, wires in the
    catalog, registry, and agent dispatch function, then passes
    ``self.handle`` to each channel plugin's polling callback and
    each webhook handler.

    Parameters
    ----------
    catalog : ChannelCatalog
        Holds registered channel plugins (for sending replies).
    registry : BindingRegistry
        Manages (channel, conversation) → ChannelSession mappings.
    agent_fn : AgentDispatchFn
        Callable that runs the agent and returns its reply.
        Signature: ``(session_key: str, text: str) -> str | None``
    allowlists : dict[str, AllowlistPolicy | None]
        Per-channel allowlist policies (from operator config).
        Key is channel_id; ``None`` means allow all.
    """

    def __init__(
        self,
        catalog: ChannelCatalog,
        registry: BindingRegistry,
        agent_fn: AgentDispatchFn,
        config: JarvisConfig,
        *,
        allowlists: dict[str, AllowlistPolicy | None] | None = None,
        session_store: SessionStore | None = None,
    ) -> None:
        self._catalog = catalog
        self._registry = registry
        self._agent_fn = agent_fn
        self._config = config
        self._allowlists: dict[str, AllowlistPolicy | None] = allowlists or {}
        self._session_store = session_store
        # Semaphore map: one slot per session_key so concurrent messages
        # from the same conversation are serialized.
        self._session_locks: dict[str, threading.Lock] = {}
        self._mu = threading.Lock()

    def _session_lock(self, session_key: str) -> threading.Lock:
        """Return the per-session lock, creating it if necessary."""
        with self._mu:
            if session_key not in self._session_locks:
                self._session_locks[session_key] = threading.Lock()
            return self._session_locks[session_key]

    def set_allowlist(self, channel_id: str, policy: AllowlistPolicy | None) -> None:
        """Update the allowlist for a channel at runtime."""
        self._allowlists[channel_id] = policy

    def handle(self, message: InboundMessage) -> str | None:
        """Handle one inbound message end-to-end.

        Steps:
        1. Allowlist check — drop if sender is not allowed.
        2. Get or create session.
        3. Acquire per-session lock (serialize concurrent messages).
        4. Run the agent.
        5. Send reply(ies) back through the channel.

        Returns the agent reply text (for tests), or None if dropped.
        """
        # 1. Allowlist.
        policy = self._allowlists.get(message.channel_id)
        if not is_allowed(message.sender_id, None, policy):
            _log.info(
                "binding_router: dropped message from %s on %s (not in allowlist)",
                message.sender_id,
                message.channel_id,
            )
            return None

        # 2. Session and Agent Resolution.
        # Check for broadcast groups
        if message.peer_kind in ("group", "channel") and message.peer_id in self._config.broadcast.groups:
            agent_ids = self._config.broadcast.groups[message.peer_id]
        else:
            agent_ids = [resolve_agent(message, self._config)]

        # Dispatch to all resolved agents
        replies = []
        for agent_id in agent_ids:
            session_key = derive_session_key(message, agent_id, self._config)
            session = self._registry.get_or_create(message, session_key=session_key)

            # 3. Per-session serialization.
            lock = self._session_lock(session.session_key)
            with lock:
                reply = self._dispatch(message, session.session_key)
                if reply:
                    replies.append(reply)
                    
        return "\n".join(replies) if replies else None

    def _dispatch(self, message: InboundMessage, session_key: str) -> str | None:
        """Run agent and send reply (called with session lock held)."""
        text = message.text.strip()
        if not text:
            _log.debug("binding_router: skipping empty message from %s", message.sender_id)
            return None

        # ── Channel Docking Interceptor ──
        if text.startswith("/dock_"):
            target_channel = text[len("/dock_"):].strip()
            if not target_channel:
                reply_text = "Missing channel name. Usage: /dock_<channel>"
                self._send_reply(message, reply_text)
                return reply_text
            
            if message.peer_kind != "user":
                reply_text = "Docking only works from a direct chat."
                self._send_reply(message, reply_text)
                return reply_text

            if not self._catalog.is_registered(target_channel):
                reply_text = f"Unknown channel plugin {target_channel}."
                self._send_reply(message, reply_text)
                return reply_text

            identity_links = getattr(self._config.session, "identityLinks", {})
            sender_full_id = f"{message.channel_id}:{message.sender_id}"
            
            # Find the user's identity group
            identity_group = None
            for group_name, links in identity_links.items():
                if sender_full_id in links:
                    identity_group = links
                    break

            if not identity_group:
                reply_text = f"No linked identity found for {target_channel}."
                self._send_reply(message, reply_text)
                return reply_text

            # Find the target peer ID in the identity group
            target_peer = None
            prefix = f"{target_channel}:"
            for link in identity_group:
                if link.startswith(prefix):
                    target_peer = link[len(prefix):]
                    break

            if not target_peer:
                reply_text = f"No linked identity found for {target_channel}."
                self._send_reply(message, reply_text)
                return reply_text

            if self._session_store is not None:
                self._session_store.append_entry(session_key, {
                    "role": "system",
                    "payload": {"text": f"Session docked to {target_channel}"},
                    "lastChannel": target_channel,
                    "lastTo": target_peer,
                })
            else:
                _log.warning("binding_router: session_store not wired, docking state not persisted.")

            reply_text = f"Docked. Future replies for this session will go to {target_channel}."
            self._send_reply(message, reply_text)
            return reply_text

        plugin = self._catalog.get(message.channel_id)
        if plugin is None:
            _log.warning(
                "binding_router: no plugin for channel %s; cannot reply",
                message.channel_id,
            )
            return None

        # Start presence emitter (typing indicator) if the channel supports it.
        raw_typing = plugin.raw.get("send_typing")
        presence: PresenceEmitter | None = None
        if callable(raw_typing):
            presence = PresenceEmitter(
                send_fn=raw_typing,
                conversation_id=message.conversation_id,
            )
            presence.start()

        try:
            reply_text = self._agent_fn(session_key, message.text)
        except Exception as e:  # noqa: BLE001
            _log.warning("binding_router: agent_fn error: %s", e)
            reply_text = None
        finally:
            if presence is not None:
                presence.stop()

        if not reply_text:
            return None

        self._send_reply(message, reply_text)
        return reply_text

    def _send_reply(self, message: InboundMessage, reply_text: str) -> None:
        plugin = self._catalog.get(message.channel_id)
        if plugin is None:
            return
            
        chunks = split_reply(reply_text, channel_id=message.channel_id)
        for chunk in chunks:
            try:
                plugin.send(message.conversation_id, chunk)
            except Exception as e:  # noqa: BLE001
                _log.warning(
                    "binding_router: send failed on %s: %s",
                    message.channel_id,
                    e,
                )

    def make_callback(
        self, channel_id: str
    ) -> Callable[[dict[str, Any]], None]:
        """Return a ``callback(raw_dict)`` for a channel plugin's ``listen()``.

        The callback converts the channel's raw update dict to an
        ``InboundMessage`` and calls ``self.handle()``.

        The raw dict from ``listen()`` is channel-specific. For Telegram
        it has keys: ``chat_id``, ``text``, ``from_id``, ``message_id``.
        We normalize to the canonical ``InboundMessage`` shape.
        """

        def _callback(raw: dict[str, Any]) -> None:
            try:
                msg = InboundMessage(
                    channel_id=channel_id,
                    conversation_id=str(raw.get("chat_id", raw.get("conversation_id", ""))),
                    sender_id=str(raw.get("from_id", raw.get("sender_id", ""))),
                    text=str(raw.get("text", "")),
                    kind="text",
                    raw=raw,
                    peer_kind=str(raw.get("peer_kind", "user")),
                    peer_id=str(raw.get("peer_id", "")),
                    thread_id=str(raw.get("thread_id", "")) if raw.get("thread_id") else None,
                    is_owner=bool(raw.get("is_owner", False)),
                    location=raw.get("location"),
                )
                if msg.location:
                    text = format_inbound_location(msg.text, msg.location)
                    # Create a new InboundMessage with the updated text
                    msg = InboundMessage(
                        channel_id=msg.channel_id,
                        conversation_id=msg.conversation_id,
                        sender_id=msg.sender_id,
                        text=text,
                        kind="location",
                        raw=msg.raw,
                        peer_kind=msg.peer_kind,
                        peer_id=msg.peer_id,
                        thread_id=msg.thread_id,
                        is_owner=msg.is_owner,
                        location=msg.location,
                    )
                self.handle(msg)
            except Exception as e:  # noqa: BLE001
                _log.warning("binding_router: callback error on %s: %s", channel_id, e)

        return _callback


__all__ = ["AgentDispatchFn", "BindingRouter"]
