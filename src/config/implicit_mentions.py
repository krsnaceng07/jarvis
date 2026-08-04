"""jarvis.config.implicit_mentions — channel implicit-mention policy resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/implicit-mentions.ts``.
"""
from __future__ import annotations

from typing import Optional, TypedDict


class ChannelImplicitMentionsConfig(TypedDict, total=False):
    replyToBot: bool
    quotedBot: bool
    threadParticipation: bool


class ResolvedChannelImplicitMentions(TypedDict):
    replyToBot: bool
    quotedBot: bool
    threadParticipation: bool


#: Shipped defaults applied when no config override is present.
SHIPPED_IMPLICIT_MENTION_DEFAULTS: ResolvedChannelImplicitMentions = {
    "replyToBot": True,
    "quotedBot": True,
    "threadParticipation": True,
}


def _resolve_account_entry(accounts, account_id) -> Optional[dict]:
    if not isinstance(accounts, dict):
        return None
    if not account_id:
        return None
    return accounts.get(account_id)


def _pick(account_value, channel_value, default_value, shipped_value):
    """Pick the first non-None value in account > channel > defaults > shipped.

    Mirrors the OpenClaw ``??`` nullish-coalescing chain — explicit ``False``
    must not be treated as missing.
    """
    for candidate in (account_value, channel_value, default_value, shipped_value):
        if candidate is not None:
            return candidate
    return shipped_value


def resolve_channel_implicit_mentions(params: dict) -> ResolvedChannelImplicitMentions:
    """Resolve each implicit-mention kind using account > channel > defaults > shipped.

    Mirrors :func:`resolveChannelImplicitMentions`
    (``shared/config/implicit-mentions.ts``).
    """
    cfg = params.get("cfg") or {}
    channel = params.get("channel")
    if not isinstance(cfg, dict) or not channel:
        return dict(SHIPPED_IMPLICIT_MENTION_DEFAULTS)
    channels = cfg.get("channels") or {}
    channel_config = channels.get(channel) if isinstance(channels, dict) else None
    if not isinstance(channel_config, dict):
        return dict(SHIPPED_IMPLICIT_MENTION_DEFAULTS)
    accounts = channel_config.get("accounts")
    account_config = _resolve_account_entry(accounts, str(params.get("accountId") or "").strip().lower() or None) or {}
    defaults = (cfg.get("channels") or {}).get("defaults", {}).get("implicitMentions") or {}
    return {
        "replyToBot": _pick(
            (account_config.get("implicitMentions") or {}).get("replyToBot"),
            channel_config.get("implicitMentions", {}).get("replyToBot"),
            defaults.get("replyToBot"),
            SHIPPED_IMPLICIT_MENTION_DEFAULTS["replyToBot"],
        ),
        "quotedBot": _pick(
            (account_config.get("implicitMentions") or {}).get("quotedBot"),
            channel_config.get("implicitMentions", {}).get("quotedBot"),
            defaults.get("quotedBot"),
            SHIPPED_IMPLICIT_MENTION_DEFAULTS["quotedBot"],
        ),
        "threadParticipation": _pick(
            (account_config.get("implicitMentions") or {}).get("threadParticipation"),
            channel_config.get("implicitMentions", {}).get("threadParticipation"),
            defaults.get("threadParticipation"),
            SHIPPED_IMPLICIT_MENTION_DEFAULTS["threadParticipation"],
        ),
    }


__all__ = [
    "ChannelImplicitMentionsConfig",
    "ResolvedChannelImplicitMentions",
    "SHIPPED_IMPLICIT_MENTION_DEFAULTS",
    "resolve_channel_implicit_mentions",
]
