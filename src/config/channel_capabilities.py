"""jarvis.config.channel_capabilities — channel capability normalization.

OpenClaw parity: mirrors ``openclaw-main/src/config/channel-capabilities.ts``.
"""
from __future__ import annotations

from typing import List, Optional


def _is_string_array(value) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _normalize_capabilities(capabilities) -> Optional[List[str]]:
    if not _is_string_array(capabilities):
        return None
    out = [v.strip() for v in capabilities if v.strip()]
    return out or None


def _resolve_account_capabilities(params: dict) -> Optional[List[str]]:
    cfg = params.get("cfg")
    if not cfg or not isinstance(cfg, dict):
        return None
    account_id = params.get("accountId")
    normalized_account = str(account_id or "").strip().lower() or None
    accounts = cfg.get("accounts")
    if isinstance(accounts, dict):
        match = None
        if normalized_account is not None:
            match = accounts.get(normalized_account)
        if not match and accounts:
            # Fall back to first matching string-keyed entry.
            for k, v in accounts.items():
                if isinstance(v, dict):
                    match = v
                    break
        if isinstance(match, dict):
            account_caps = _normalize_capabilities(match.get("capabilities"))
            if account_caps is not None:
                return account_caps
    return _normalize_capabilities(cfg.get("capabilities"))


def resolve_channel_capabilities(params: dict) -> Optional[List[str]]:
    """Resolve normalized string capabilities for a channel/account config pair.

    Mirrors :func:`resolveChannelCapabilities`
    (``shared/config/channel-capabilities.ts``).
    """
    cfg = params.get("cfg")
    channel = params.get("channel")
    if not cfg or not channel:
        return None
    channels = cfg.get("channels") if isinstance(cfg, dict) else None
    channel_config = None
    if isinstance(channels, dict):
        channel_config = channels.get(channel)
    if not isinstance(channel_config, dict):
        channel_config = cfg.get(channel) if isinstance(cfg, dict) else None
    if not isinstance(channel_config, dict):
        return None
    return _resolve_account_capabilities({
        "cfg": channel_config,
        "accountId": params.get("accountId"),
    })


__all__ = ["resolve_channel_capabilities"]
