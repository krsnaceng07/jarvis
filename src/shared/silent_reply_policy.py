"""jarvis.shared.silent_reply_policy — silent-reply classification.

OpenClaw parity: mirrors ``openclaw-main/src/shared/silent-reply-policy.ts``.
"""
from __future__ import annotations

from typing import Literal, Optional, TypedDict

SilentReplyPolicy = Literal["allow", "disallow"]
SilentReplyConversationType = Literal["direct", "group", "internal"]


class SilentReplyPolicyShape(TypedDict, total=False):
    group: SilentReplyPolicy
    internal: SilentReplyPolicy


DEFAULT_SILENT_REPLY_POLICY: dict = {
    "direct": "disallow",
    "group": "allow",
    "internal": "allow",
}


def _normalize_lowercase_string_or_empty(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def classify_silent_reply_conversation_type(params: dict) -> str:
    """Classify a reply context for silent-reply policy.

    Mirrors :func:`classifySilentReplyConversationType`
    (``shared/silent-reply-policy.ts``).
    """
    if params.get("conversationType") in ("direct", "group", "internal"):
        return params["conversationType"]
    key = _normalize_lowercase_string_or_empty(params.get("sessionKey"))
    if ":group:" in key or ":channel:" in key:
        return "group"
    if ":direct:" in key or ":dm:" in key:
        return "direct"
    surface = _normalize_lowercase_string_or_empty(params.get("surface"))
    if surface == "webchat":
        return "direct"
    return "internal"


def resolve_silent_reply_policy_from_policies(params: dict) -> str:
    """Resolve the silent-reply policy with surface overrides.

    Direct chats are never silently swallowed, regardless of config overlays.

    Mirrors :func:`resolveSilentReplyPolicyFromPolicies`
    (``shared/silent-reply-policy.ts``).
    """
    conv_type = params.get("conversationType")
    if conv_type == "direct":
        return "disallow"
    surface = (params.get("surfacePolicy") or {}).get(conv_type)
    if surface:
        return surface
    default = (params.get("defaultPolicy") or {}).get(conv_type)
    if default:
        return default
    return DEFAULT_SILENT_REPLY_POLICY.get(conv_type, "disallow")


__all__ = [
    "SilentReplyPolicy",
    "SilentReplyConversationType",
    "SilentReplyPolicyShape",
    "DEFAULT_SILENT_REPLY_POLICY",
    "classify_silent_reply_conversation_type",
    "resolve_silent_reply_policy_from_policies",
]
