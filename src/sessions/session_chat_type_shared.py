"""Session chat-type classification — shared helpers.

Mirrors OpenClaw's ``extensions/sessions/session-chat-type-shared.ts``:
the cross-module helpers for classifying chat surface from a
session key. The Python port keeps the same public surface:

- ``SessionKeyChatType`` — ``"direct" | "group" | "channel" | "unknown"``
- ``has_ambiguous_canonical_session_peer_shape`` — True when
  multiple peer shapes match
- ``parse_canonical_session_peer_shape`` — extract the
  canonical ``{channel, chat_type}`` shape
- ``derive_session_chat_type_from_key`` — best-effort
  extraction across canonical + legacy formats
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from .session_key_utils import parse_agent_session_key

SessionKeyChatType = Literal["direct", "group", "channel", "unknown"]
CanonicalPeerKind = Literal["direct", "dm", "group", "channel"]

# Closed set of canonical peer kinds. Mirrors the TS
# ``CANONICAL_PEER_KINDS`` constant.
_CANONICAL_PEER_KINDS: frozenset[str] = frozenset({"direct", "dm", "group", "channel"})


def _is_canonical_peer_kind(value: object) -> bool:
    """True when ``value`` is a recognized canonical peer kind string."""
    if not isinstance(value, str):
        return False
    return value in _CANONICAL_PEER_KINDS


@dataclass(frozen=True, slots=True)
class CanonicalSessionPeerShape:
    """Canonical peer shape: channel (optional) + chat type.

    Mirrors the TS ``CanonicalSessionPeerShape`` type.
    """

    chat_type: Literal["direct", "group", "channel"]
    channel: Optional[str] = None


# ── Ambiguity check ────────────────────────────────────────────────


# Built-in legacy chat-type patterns. Mirrors the TS
# ``deriveBuiltInLegacySessionChatType`` regex set.
_LEGACY_GROUP_PATTERN = re.compile(r"^group:[^:]+(?::.*)?$")
_LEGACY_CHANNEL_PATTERN = re.compile(r"^channel:[^:]+(?::.*)?$")
_LEGACY_WHATSAPP_GROUP_PATTERN = re.compile(r"^(?:whatsapp:)?[^:]+@g\.us$")
_LEGACY_DISCORD_CHANNEL_PATTERN = re.compile(
    r"^discord:(?:[^:]+:)?guild-[^:]+:channel-[^:]+$"
)


def _derive_built_in_legacy_session_chat_type(
    scoped_session_key: str,
) -> Optional[SessionKeyChatType]:
    """Built-in legacy chat-type derivation.

    Mirrors ``deriveBuiltInLegacySessionChatType``.
    """
    if _LEGACY_GROUP_PATTERN.match(scoped_session_key):
        return "group"
    if _LEGACY_CHANNEL_PATTERN.match(scoped_session_key):
        return "channel"
    if _LEGACY_WHATSAPP_GROUP_PATTERN.match(scoped_session_key):
        return "group"
    if _LEGACY_DISCORD_CHANNEL_PATTERN.match(scoped_session_key):
        return "channel"
    return None


def has_ambiguous_canonical_session_peer_shape(scoped_session_key: str) -> bool:
    """True when more than one canonical peer shape matches.

    Mirrors ``hasAmbiguousCanonicalSessionPeerShape``:
    if multiple of the bare-direct / channel / account /
    built-in-legacy shapes match, the key is ambiguous and
    must not be trusted for routing.
    """
    parts = scoped_session_key.split(":")
    if parts and parts[0] == "agent":
        return False
    has_bare_direct_peer_shape = bool(
        (parts and parts[0] in ("direct", "dm")) and len(parts) > 1 and parts[1]
    )
    has_channel_peer_shape = bool(
        parts
        and parts[0]
        and len(parts) > 1
        and _is_canonical_peer_kind(parts[1])
        and len(parts) > 2
        and parts[2]
    )
    has_account_peer_shape = bool(
        len(parts) > 3
        and parts[0]
        and parts[1]
        and _is_canonical_peer_kind(parts[2])
        and parts[3]
    )
    has_built_in_legacy_peer_shape = (
        _derive_built_in_legacy_session_chat_type(scoped_session_key) is not None
    )
    matches = [
        has_bare_direct_peer_shape,
        has_channel_peer_shape,
        has_account_peer_shape,
        has_built_in_legacy_peer_shape,
    ]
    return sum(1 for m in matches if m) > 1


# ── Canonical shape parser ────────────────────────────────────────


def parse_canonical_session_peer_shape(
    scoped_session_key: str,
) -> Optional[CanonicalSessionPeerShape]:
    """Extract the canonical ``{channel, chat_type}`` shape.

    Mirrors ``parseCanonicalSessionPeerShape``: returns
    ``None`` for ambiguous, agent-wrapped, or malformed keys.
    """
    parts = scoped_session_key.split(":")
    # A second agent wrapper is opaque plugin identity, never
    # a channel route.
    if (parts and parts[0] == "agent") or has_ambiguous_canonical_session_peer_shape(
        scoped_session_key
    ):
        return None
    channel: Optional[str] = None
    peer_kind: Optional[str] = None
    peer_id_start = 0
    if parts and parts[0] in ("direct", "dm"):
        peer_kind = parts[0]
        peer_id_start = 1
    elif (
        parts
        and parts[0]
        and len(parts) > 1
        and _is_canonical_peer_kind(parts[1])
    ):
        channel = parts[0]
        peer_kind = parts[1]
        peer_id_start = 2
    elif (
        len(parts) > 2
        and parts[0]
        and parts[1]
        and _is_canonical_peer_kind(parts[2])
    ):
        channel = parts[0]
        peer_kind = parts[2]
        peer_id_start = 3
    # Peer ids are opaque tails; only the structural prefix +
    # first peer-id segment must be present.
    if not peer_kind or peer_id_start >= len(parts) or not parts[peer_id_start]:
        return None
    chat_type: SessionKeyChatType
    if peer_kind in ("direct", "dm"):
        chat_type = "direct"
    else:
        chat_type = peer_kind  # type: ignore[assignment]
    return CanonicalSessionPeerShape(chat_type=chat_type, channel=channel)


def _derive_canonical_session_chat_type(
    scoped_session_key: str,
) -> Optional[SessionKeyChatType]:
    return parse_canonical_session_peer_shape(scoped_session_key).chat_type if (
        parse_canonical_session_peer_shape(scoped_session_key)
    ) else None


# ── Top-level derivation ──────────────────────────────────────────


def _derive_session_chat_type_from_scoped_key(
    scoped_session_key: str,
    derive_legacy_session_chat_types: list[Callable[[str], Optional[SessionKeyChatType]]] = None,
) -> SessionKeyChatType:
    """Best-effort chat-type derivation.

    Mirrors ``deriveSessionChatTypeFromScopedKey`` (internal).
    Falls through canonical → built-in-legacy → caller-provided
    legacy derivers, returning ``"unknown"`` when nothing
    matches.
    """
    derive_legacy = derive_legacy_session_chat_types or []
    canonical = _derive_canonical_session_chat_type(scoped_session_key)
    if canonical is not None:
        return canonical
    built_in_legacy = _derive_built_in_legacy_session_chat_type(scoped_session_key)
    if built_in_legacy is not None:
        return built_in_legacy
    for derive_legacy_session_chat_type in derive_legacy:
        derived = derive_legacy_session_chat_type(scoped_session_key)
        if derived is not None:
            return derived
    return "unknown"


def derive_session_chat_type_from_key(
    session_key: object,
    derive_legacy_session_chat_types: Optional[list[Callable[[str], Optional[SessionKeyChatType]]]] = None,
) -> SessionKeyChatType:
    """Best-effort chat-type extraction from a session key.

    Mirrors ``deriveSessionChatTypeFromKey``: lowercases the
    input, strips the ``agent:<id>:`` wrapper (via
    ``parse_agent_session_key``), then derives the chat
    type from the scoped body.
    """
    if not isinstance(session_key, str):
        return "unknown"
    raw = session_key.strip().lower()
    if not raw:
        return "unknown"
    parsed = parse_agent_session_key(raw)
    scoped = parsed.rest if parsed is not None else raw
    return _derive_session_chat_type_from_scoped_key(
        scoped, derive_legacy_session_chat_types or []
    )


__all__ = [
    "CanonicalSessionPeerShape",
    "SessionKeyChatType",
    "derive_session_chat_type_from_key",
    "has_ambiguous_canonical_session_peer_shape",
    "parse_canonical_session_peer_shape",
]
