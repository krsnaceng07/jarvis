"""Channel types — inbound/outbound message shapes.

Mirrors OpenClaw's ``src/channels/chat-type.ts``,
``src/channels/session-envelope.ts``, and
``src/channels/chat-message.ts``.

These are the typed shapes that flow between the channel plugin,
the gateway, and the agent session. Plugins should use these types
in their ``send()`` and ``on_message()`` callbacks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


# ── Message types ──────────────────────────────────────────────────────


MessageKind = Literal["text", "image", "audio", "video", "file", "action", "location"]


@dataclass(frozen=True, slots=True)
class NormalizedLocation:
    """A normalized geographical location.
    
    Mirrors OpenClaw's NormalizedLocation structure for portable location payload.
    """
    latitude: float
    longitude: float
    accuracy_m: Optional[int] = None
    source: Literal["pin", "place", "live"] = "pin"
    name: Optional[str] = None
    address: Optional[str] = None
    caption: Optional[str] = None
    is_live: bool = False


@dataclass(frozen=True, slots=True)
class InboundMessage:
    """A message received from a channel.

    Mirrors OpenClaw's ``InboundChatMessage`` / ``SessionEnvelope``.

    Attributes
    ----------
    channel_id : str
        The channel plugin id (e.g. ``"telegram"``, ``"discord"``).
    conversation_id : str
        Channel-native conversation / chat id. Used to route replies
        back to the right thread.
    sender_id : str
        Channel-native user id of the sender.
    text : str
        Plaintext message body (empty string for media-only messages).
    kind : MessageKind
        Message type discriminator.
    raw : dict
        The raw channel payload (for channel plugins that need it).
    is_owner : bool
        True when the sender is the operator (matches allow-from config).
    attachments : list[dict]
        Optional media attachments (image, audio, etc.).
    """

    channel_id: str
    conversation_id: str
    sender_id: str
    text: str = ""
    kind: MessageKind = "text"
    raw: dict = field(default_factory=dict)
    is_owner: bool = False
    attachments: list[dict] = field(default_factory=list)
    location: Optional[NormalizedLocation] = None
    peer_kind: str = "user"
    peer_id: str = ""
    account_id: Optional[str] = None
    guild_id: Optional[str] = None
    team_id: Optional[str] = None
    thread_id: Optional[str] = None


@dataclass(frozen=True, slots=True)
class OutboundMessage:
    """A message to send through a channel.

    Mirrors OpenClaw's ``OutboundChatMessage``.

    Attributes
    ----------
    channel_id : str
        Target channel plugin id.
    conversation_id : str
        Target conversation / chat id.
    text : str
        Plaintext (or markdown) body.
    kind : MessageKind
        Message type discriminator.
    reply_to_id : str | None
        Channel-native message id to reply to (optional).
    attachments : list[dict]
        Optional media attachments.
    location : NormalizedLocation | None
        Optional geographical location.
    metadata : dict
        Channel-specific metadata (e.g. ``parse_mode`` for Telegram).
    """

    channel_id: str
    conversation_id: str
    text: str = ""
    kind: MessageKind = "text"
    reply_to_id: str | None = None
    attachments: list[dict] = field(default_factory=list)
    location: Optional[NormalizedLocation] = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Session envelope ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ChannelSession:
    """A channel session envelope — the context for one conversation.

    Mirrors OpenClaw's ``ChannelSessionEnvelope``. The channel router
    creates or looks up a ChannelSession for each inbound message and
    passes it to the agent session bootstrap.

    Attributes
    ----------
    channel_id : str
        Channel plugin id.
    session_key : str
        Stable key for this conversation (e.g. ``"telegram:123456789"``).
    conversation_id : str
        Channel-native conversation id.
    agent_id : str
        The JARVIS agent handling this session.
    is_owner : bool
        Whether the session is owned by the operator.
    """

    channel_id: str
    session_key: str
    conversation_id: str
    agent_id: str = "default"
    is_owner: bool = False


# ── Channel Route ──────────────────────────────────────────────────────


ChannelRouteChatType = Literal["direct", "group", "channel"]
ChannelRouteThreadKind = Literal["topic", "thread", "reply"]
ChannelRouteThreadSource = Literal["explicit", "target", "session", "turn"]


@dataclass(frozen=True, slots=True)
class ChannelRouteTarget:
    to: str
    raw_to: Optional[str] = None
    chat_type: Optional[ChannelRouteChatType] = None


@dataclass(frozen=True, slots=True)
class ChannelRouteThread:
    id: str | int
    kind: Optional[ChannelRouteThreadKind] = None
    source: Optional[ChannelRouteThreadSource] = None


@dataclass(frozen=True, slots=True)
class ChannelRouteRef:
    channel: Optional[str] = None
    account_id: Optional[str] = None
    target: Optional[ChannelRouteTarget] = None
    thread: Optional[ChannelRouteThread] = None


@dataclass(frozen=True, slots=True)
class ConversationRef:
    channel: str
    conversation_id: str
    parent_conversation_id: Optional[str] = None
    account_id: Optional[str] = None


# ── Session Bindings ───────────────────────────────────────────────────


BindingTargetKind = Literal["subagent", "session"]
BindingStatus = Literal["active", "ending", "ended"]
SessionBindingPlacement = Literal["current", "child"]


@dataclass(frozen=True, slots=True)
class SessionBindingRecord:
    binding_id: str
    target_session_key: str
    target_kind: BindingTargetKind
    conversation: ConversationRef
    status: BindingStatus
    bound_at: float
    expires_at: Optional[float] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionBindingBindInput:
    target_session_key: str
    target_kind: BindingTargetKind
    conversation: ConversationRef
    placement: Optional[SessionBindingPlacement] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    ttl_ms: Optional[int] = None


@dataclass(frozen=True, slots=True)
class SessionBindingUnbindInput:
    reason: str
    binding_id: Optional[str] = None
    target_session_key: Optional[str] = None


__all__ = [
    "MessageKind",
    "InboundMessage",
    "OutboundMessage",
    "ChannelSession",
    "ChannelRouteChatType",
    "ChannelRouteThreadKind",
    "ChannelRouteThreadSource",
    "ChannelRouteTarget",
    "ChannelRouteThread",
    "ChannelRouteRef",
    "ConversationRef",
    "BindingTargetKind",
    "BindingStatus",
    "SessionBindingPlacement",
    "SessionBindingRecord",
    "SessionBindingBindInput",
    "SessionBindingUnbindInput",
]
