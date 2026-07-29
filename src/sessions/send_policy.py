"""Session send policy helpers decide when session output can be sent to targets.

Mirrors OpenClaw's ``src/sessions/send-policy.ts``:

- ``normalizeSendPolicy`` — parse raw policy text into a
  ``"allow" | "deny"`` decision (lowercased).
- ``resolveSendPolicy`` — resolve the per-session send
  decision from a per-session ``entry.sendPolicy`` override
  and the global ``session.sendPolicy`` config rules.

The matcher is a small DSL with four matchers:
- ``channel`` — exact match against the channel id
- ``chatType`` — exact match against the chat type
- ``keyPrefix`` — prefix match against the (raw or
  agent-prefix-stripped) session key
- ``rawKeyPrefix`` — prefix match against the raw session key
  (the agent prefix is NOT stripped for this matcher)

Public surface (mirrors the TS source):
- ``normalize_send_policy(raw)`` — ``"allow" | "deny" | None``
- ``resolve_send_policy(params)`` — final decision

Python adaptations (documented in code):
- TS string-literal unions → Python ``Literal[...]`` +
  ``frozenset`` membership sets
- The ``OpenClawConfig`` is passed in as a plain ``dict``;
  the helpers only touch the small slice they need
- ``normalizeLowercaseStringOrEmpty`` is inlined as
  ``_lower_or_empty`` (the host passes the value, so the
  inline call is the same shape)
- The ``SessionEntry`` is passed as a plain ``dict``
"""
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

from jarvis_normalization_core.string_coerce import (
    normalize_lowercase_string_or_empty,
    normalize_optional_lowercase_string,
)

from src.sessions.session_chat_type import derive_session_chat_type
from src.sessions.session_chat_type_shared import (
    has_ambiguous_canonical_session_peer_shape,
    parse_canonical_session_peer_shape,
)

# Literal unions + closed-set membership constants.
SessionSendPolicyDecision = Literal["allow", "deny"]
SessionChatType = Literal["direct", "group", "channel", "unknown"]
ChatType = Literal["direct", "group", "channel"]

VALID_SEND_POLICY_VALUES: frozenset[str] = frozenset({"allow", "deny"})
VALID_CHAT_TYPES: frozenset[str] = frozenset({"direct", "group", "channel"})


class SessionEntry(TypedDict, total=False):
    sessionId: str
    updatedAt: int
    sendPolicy: str
    channel: str
    lastChannel: str
    chatType: str


class SessionSendPolicyRuleMatch(TypedDict, total=False):
    channel: str
    chatType: str
    keyPrefix: str
    rawKeyPrefix: str


class SessionSendPolicyRule(TypedDict, total=False):
    action: str
    match: SessionSendPolicyRuleMatch


class SessionSendPolicy(TypedDict, total=False):
    default: str
    rules: list[SessionSendPolicyRule]


class OpenClawConfig(TypedDict, total=False):
    session: dict[str, Any]


# ── Helpers ────────────────────────────────────────────────


def normalize_chat_type(raw: object) -> Optional[ChatType]:
    """Normalize a channel chat-type label to the OpenClaw vocabulary.

    Mirrors ``normalizeChatType`` from ``../channels/chat-type.ts``.
    """
    value = normalize_optional_lowercase_string(raw)
    if not value:
        return None
    if value in ("direct", "dm"):
        return "direct"
    if value == "group":
        return "group"
    if value == "channel":
        return "channel"
    return None


def normalize_send_policy(
    raw: Optional[str],
) -> Optional[SessionSendPolicyDecision]:
    """Normalize a raw policy string to ``"allow"`` / ``"deny"`` / ``None``.

    Mirrors ``normalizeSendPolicy``.
    """
    value = normalize_optional_lowercase_string(raw)
    if value == "allow":
        return "allow"
    if value == "deny":
        return "deny"
    return None


def _normalize_match_value(raw: object) -> Optional[str]:
    """Lowercased, trimmed match value; ``None`` for empty/non-string."""
    value = normalize_optional_lowercase_string(raw)
    return value or None


def _strip_agent_session_key_prefix(key: Optional[str]) -> Optional[str]:
    """Strip the canonical ``agent:<agentId>:`` prefix from a session key.

    Mirrors the private ``stripAgentSessionKeyPrefix`` helper.
    """
    if not key:
        return None
    parts = key.split(":")
    if parts and parts[0] == "agent":
        if len(parts) < 3 or not parts[1] or not parts[2]:
            return None
        return ":".join(parts[2:])
    return key


def _derive_channel_from_key(key: Optional[str]) -> Optional[str]:
    """Derive the channel id from a session key, if it is canonical-shaped."""
    normalized_key = _strip_agent_session_key_prefix(key)
    if not normalized_key:
        return None
    parsed = parse_canonical_session_peer_shape(normalized_key)
    if parsed is None:
        return None
    return _normalize_match_value(parsed.channel)


def _derive_chat_type_from_key(key: Optional[str]) -> Optional[SessionChatType]:
    """Derive the chat type from a session key via the legacy deriver."""
    normalized_key = normalize_optional_lowercase_string(
        _strip_agent_session_key_prefix(key)
    )
    if not normalized_key or normalized_key.startswith("agent:"):
        return None
    derived = derive_session_chat_type(normalized_key)
    if derived != "unknown":
        return derived
    return None


def _has_ambiguous_peer_shape(key: Optional[str]) -> bool:
    """Return ``True`` when the legacy key grammar is ambiguous.

    The legacy key grammar cannot distinguish a peer-kind-shaped
    account id from a channel peer. Such keys are flagged
    ambiguous so a deny policy cannot be silently satisfied.
    """
    normalized_key = normalize_optional_lowercase_string(
        _strip_agent_session_key_prefix(key)
    )
    if not normalized_key:
        return False
    return has_ambiguous_canonical_session_peer_shape(normalized_key)


# ── Public surface ────────────────────────────────────────


def resolve_send_policy(
    *,
    cfg: dict[str, Any],
    entry: Optional[dict[str, Any]] = None,
    session_key: Optional[str] = None,
    channel: Optional[str] = None,
    chat_type: Optional[str] = None,
) -> SessionSendPolicyDecision:
    """Resolve the per-session send policy decision.

    Mirrors ``resolveSendPolicy`` in OpenClaw. The order of
    resolution is:
    1. ``entry.sendPolicy`` override (always wins).
    2. Ambiguous peer shape → ``"deny"`` (legacy keys cannot
       safely satisfy an allow policy).
    3. The first matching rule in ``session.sendPolicy.rules``
       — ``"deny"`` rules short-circuit, ``"allow"`` rules
       mark the session as allowed.
    4. The default policy (``session.sendPolicy.default``),
       or ``"allow"`` if no default is set.
    """
    override = normalize_send_policy(entry.get("sendPolicy") if entry else None)
    if override is not None:
        return override

    session = cfg.get("session") or {}
    policy = session.get("sendPolicy") or {}
    if not policy:
        return "allow"

    if _has_ambiguous_peer_shape(session_key):
        return "deny"

    raw_session_key = session_key or ""
    stripped_session_key = _strip_agent_session_key_prefix(raw_session_key) or ""
    raw_session_key_norm = normalize_lowercase_string_or_empty(raw_session_key)
    stripped_session_key_norm = normalize_lowercase_string_or_empty(stripped_session_key)

    cached_channel: Optional[str] = None
    cached_chat_type: Optional[SessionChatType] = None

    def _get_channel() -> Optional[str]:
        nonlocal cached_channel
        if cached_channel is None:
            cached_channel = (
                _normalize_match_value(channel)
                or _normalize_match_value(entry.get("channel") if entry else None)
                or _normalize_match_value(entry.get("lastChannel") if entry else None)
                or _derive_channel_from_key(session_key)
            )
        return cached_channel

    def _get_chat_type() -> Optional[SessionChatType]:
        nonlocal cached_chat_type
        if cached_chat_type is None:
            cached_chat_type = (
                normalize_chat_type(chat_type)
                or normalize_chat_type(entry.get("chatType") if entry else None)
                or _derive_chat_type_from_key(session_key)
            )
        return cached_chat_type

    allowed_match = False
    for rule in policy.get("rules") or []:
        if not rule:
            continue
        action = normalize_send_policy(rule.get("action")) or "allow"
        match = rule.get("match") or {}
        match_channel = _normalize_match_value(match.get("channel"))
        match_chat_type = normalize_chat_type(match.get("chatType"))
        match_prefix = _normalize_match_value(match.get("keyPrefix"))
        match_raw_prefix = _normalize_match_value(match.get("rawKeyPrefix"))

        if match_channel and match_channel != _get_channel():
            continue
        if match_chat_type and match_chat_type != _get_chat_type():
            continue
        if match_raw_prefix and not raw_session_key_norm.startswith(match_raw_prefix):
            continue
        if (
            match_prefix
            and not raw_session_key_norm.startswith(match_prefix)
            and not stripped_session_key_norm.startswith(match_prefix)
        ):
            continue
        if action == "deny":
            return "deny"
        allowed_match = True

    if allowed_match:
        return "allow"

    fallback = normalize_send_policy(policy.get("default"))
    return fallback or "allow"


__all__ = [
    "ChatType",
    "OpenClawConfig",
    "SessionChatType",
    "SessionEntry",
    "SessionSendPolicy",
    "SessionSendPolicyDecision",
    "SessionSendPolicyRule",
    "SessionSendPolicyRuleMatch",
    "VALID_CHAT_TYPES",
    "VALID_SEND_POLICY_VALUES",
    "normalize_chat_type",
    "normalize_send_policy",
    "resolve_send_policy",
]
