"""jarvis.config.context_visibility — context visibility mode resolution.

OpenClaw parity: mirrors ``openclaw-main/src/config/context-visibility.ts``.
"""
from __future__ import annotations

from typing import Any, Optional


ContextVisibilityMode = str  # "all" | "tag" | "none"


def resolve_default_context_visibility(cfg: dict) -> Optional[ContextVisibilityMode]:
    """Read the global channel default context visibility mode.

    Mirrors :func:`resolveDefaultContextVisibility`
    (``shared/config/context-visibility.ts``).
    """
    if not isinstance(cfg, dict):
        return None
    return cfg.get("channels", {}).get("defaults", {}).get("contextVisibility")


def _resolve_account_entry(accounts: Any, account_id: Optional[str]) -> Any:
    if not isinstance(accounts, dict):
        return None
    if account_id is None:
        return None
    return accounts.get(account_id) or accounts.get(str(account_id).lower())


def resolve_channel_context_visibility_mode(params: dict) -> ContextVisibilityMode:
    """Resolve supplemental context visibility using explicit/account/channel/default precedence.

    Mirrors :func:`resolveChannelContextVisibilityMode`
    (``shared/config/context-visibility.ts``).
    """
    configured = params.get("configuredContextVisibility")
    if configured:
        return configured
    cfg = params.get("cfg") or {}
    channel = params.get("channel")
    channel_config = (cfg.get("channels") or {}).get(channel) if channel else None
    if not isinstance(channel_config, dict):
        channel_config = None
    accounts = channel_config.get("accounts") if isinstance(channel_config, dict) else None
    account_id = params.get("accountId")
    account_mode = None
    if isinstance(accounts, dict) and account_id is not None:
        entry = _resolve_account_entry(accounts, account_id)
        if isinstance(entry, dict):
            account_mode = entry.get("contextVisibility")
    return (
        account_mode
        or (channel_config or {}).get("contextVisibility")
        or resolve_default_context_visibility(cfg)
        or "all"
    )


__all__ = [
    "ContextVisibilityMode",
    "resolve_default_context_visibility",
    "resolve_channel_context_visibility_mode",
]
