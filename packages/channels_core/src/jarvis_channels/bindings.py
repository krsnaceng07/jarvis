"""Channel bindings — session key derivation and conversation binding.

Mirrors OpenClaw's ``src/channels/session-envelope.ts``,
``src/channels/bindings.ts``, and the ``SessionKeyFactory``.

A "binding" is the link between a channel conversation (e.g. Telegram
chat_id=123456) and a JARVIS agent session. The binding:
  - Derives a stable, reproducible session key from channel + conversation id
  - Looks up or creates a ChannelSession for that key
  - Ensures one long-running session per conversation (not one per message)

The ``BindingRegistry`` is the host-side singleton that the gateway
creates once and shares between the channel router and the agent runner.
"""

from __future__ import annotations

import hashlib
import threading

from .types import (
    ChannelSession,
    InboundMessage,
    SessionBindingRecord,
    SessionBindingBindInput,
    SessionBindingUnbindInput,
    ConversationRef,
)


# ── Session key derivation ─────────────────────────────────────────────


def derive_session_key(channel_id: str, conversation_id: str) -> str:
    """Derive a stable session key from a channel + conversation id pair.

    Mirrors OpenClaw's ``deriveSessionKey`` helper. The key is
    deterministic — the same inputs always produce the same key — so
    a restarted JARVIS process can re-attach to an existing session.

    Format: ``"<channel_id>:<sha8(conversation_id)>"``
    The SHA prefix makes keys safe for filesystem use even when
    conversation_id contains special characters.

    Parameters
    ----------
    channel_id : str
        The channel plugin id (e.g. ``"telegram"``).
    conversation_id : str
        The channel-native conversation id (e.g. a Telegram chat_id).
    """
    # 8 hex chars = 32-bit prefix — collision-resistant enough for a
    # single-user assistant running one conversation per channel.
    digest = hashlib.sha256(conversation_id.encode()).hexdigest()[:8]
    return f"{channel_id}:{digest}"


def derive_webhook_path(channel_id: str) -> str:
    """Derive the gateway webhook path for a channel plugin.

    Mirrors OpenClaw's webhook path convention. The gateway registers
    this path for ``POST`` inbound updates.

    Format: ``"/v1/channels/<channel_id>/inbound"``
    """
    return f"/v1/channels/{channel_id}/inbound"


# ── Binding registry ───────────────────────────────────────────────────


class BindingRegistry:
    """Maps (channel_id, conversation_id) → ChannelSession.

    Mirrors OpenClaw's ``ChannelBindingRegistry`` from
    ``src/channels/bindings.ts``.

    The registry is the single source of truth for which JARVIS agent
    session is handling which channel conversation. It is:
      - Keyed by session_key (derived via ``derive_session_key``)
      - Thread-safe (concurrent polling threads may create sessions)
      - Process-local (sessions are re-created on restart from state DB)

    Phase W1: sessions are in-memory. Wave 2 will persist them to the
    shared state SQLite DB so sessions survive restarts.
    """

    def __init__(self, *, default_agent_id: str = "default") -> None:
        self._sessions: dict[str, ChannelSession] = {}
        self._lock = threading.Lock()
        self._default_agent_id = default_agent_id

    def get_or_create(
        self,
        message: InboundMessage,
        *,
        agent_id: str | None = None,
        session_key: str | None = None,
    ) -> ChannelSession:
        """Return the existing session for this message's conversation, or create one.

        Parameters
        ----------
        message : InboundMessage
            The inbound message carrying channel_id, conversation_id, is_owner.
        agent_id : str | None
            Override the agent to route this conversation to. Defaults to
            ``self._default_agent_id``.
        session_key : str | None
            The OpenClaw deterministic session key. Defaults to legacy key if not provided.
        """
        key = session_key or derive_session_key(message.channel_id, message.conversation_id)
        with self._lock:
            if key in self._sessions:
                return self._sessions[key]
            session = ChannelSession(
                channel_id=message.channel_id,
                session_key=key,
                conversation_id=message.conversation_id,
                agent_id=agent_id or self._default_agent_id,
                is_owner=message.is_owner,
            )
            self._sessions[key] = session
            return session

    def get(self, session_key: str) -> ChannelSession | None:
        """Return the session for ``session_key``, or None."""
        with self._lock:
            return self._sessions.get(session_key)

    def get_by_conversation(self, channel_id: str, conversation_id: str) -> ChannelSession | None:
        """Return the session for a channel + conversation id pair, or None."""
        key = derive_session_key(channel_id, conversation_id)
        return self.get(key)

    def remove(self, session_key: str) -> None:
        """Remove a session (called on session end hook)."""
        with self._lock:
            self._sessions.pop(session_key, None)

    def all_sessions(self) -> list[ChannelSession]:
        """Return a snapshot of all active sessions."""
        with self._lock:
            return list(self._sessions.values())

    def session_count(self) -> int:
        """Return the number of active channel sessions."""
        with self._lock:
            return len(self._sessions)

    def clear(self) -> None:
        """Clear all sessions (tests / shutdown only)."""
        with self._lock:
            self._sessions.clear()


# ── Convenience builder ────────────────────────────────────────────────


def session_from_message(
    message: InboundMessage,
    *,
    agent_id: str = "default",
) -> ChannelSession:
    """Build a ``ChannelSession`` for a single inbound message.

    Convenience shortcut when a ``BindingRegistry`` is not in scope.
    Does NOT cache — use ``BindingRegistry.get_or_create`` in the host.
    """
    return ChannelSession(
        channel_id=message.channel_id,
        session_key=derive_session_key(message.channel_id, message.conversation_id),
        conversation_id=message.conversation_id,
        agent_id=agent_id,
        is_owner=message.is_owner,
    )


# ── Session Binding Service ─────────────────────────────────────────────


class SessionBindingService:
    """Manages bindings between conversations and agent sessions.

    Mirrors OpenClaw's ``SessionBindingService``.
    For now, this provides a simple in-memory implementation that maps
    conversations to target sessions without adapter multiplexing.
    """

    def __init__(self) -> None:
        self._bindings: dict[str, SessionBindingRecord] = {}
        self._lock = threading.Lock()

    def bind(self, input: SessionBindingBindInput) -> SessionBindingRecord:
        """Bind a conversation to a target session."""
        binding_id = derive_session_key(
            input.conversation.channel, input.conversation.conversation_id
        )
        import time

        now = time.time()

        record = SessionBindingRecord(
            binding_id=binding_id,
            target_session_key=input.target_session_key,
            target_kind=input.target_kind,
            conversation=input.conversation,
            status="active",
            bound_at=now,
            expires_at=now + (input.ttl_ms / 1000) if input.ttl_ms else None,
            metadata=input.metadata,
        )
        with self._lock:
            self._bindings[binding_id] = record
        return record

    def list_by_session(self, target_session_key: str) -> list[SessionBindingRecord]:
        """List all bindings pointing to a target session."""
        if not target_session_key:
            return []
        with self._lock:
            return [
                b for b in self._bindings.values() if b.target_session_key == target_session_key
            ]

    def resolve_by_conversation(self, ref: ConversationRef) -> SessionBindingRecord | None:
        """Find the active binding for a conversation."""
        if not ref.channel or not ref.conversation_id:
            return None
        binding_id = derive_session_key(ref.channel, ref.conversation_id)
        with self._lock:
            return self._bindings.get(binding_id)

    def touch(self, binding_id: str, at: float | None = None) -> None:
        """Touch a binding to prevent it from expiring."""
        if not binding_id:
            return
        # Touch logic to be implemented when TTL support is fully fleshed out
        pass

    def unbind(self, input: SessionBindingUnbindInput) -> list[SessionBindingRecord]:
        """Remove bindings matching the input criteria."""
        removed = []
        with self._lock:
            for b_id, record in list(self._bindings.items()):
                if input.binding_id and record.binding_id != input.binding_id:
                    continue
                if (
                    input.target_session_key
                    and record.target_session_key != input.target_session_key
                ):
                    continue
                removed.append(record)
                del self._bindings[b_id]
        return removed


__all__ = [
    "BindingRegistry",
    "SessionBindingService",
    "derive_session_key",
    "derive_webhook_path",
    "session_from_message",
]
