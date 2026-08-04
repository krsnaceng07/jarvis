"""jarvis.config.markdown_tables — markdown table mode resolver.

OpenClaw parity: mirrors
``openclaw-main/src/config/markdown-tables.ts``.
"""
from __future__ import annotations

from typing import Any, Optional


MarkdownTableMode = str  # "off" | "bullets" | "code" | "block"


def resolve_markdown_table_mode(
    params: dict,
    *,
    normalize_channel_id=None,
    get_default_table_modes=None,
    list_channel_plugins=None,
) -> MarkdownTableMode:
    """Resolve the markdown table mode for a channel/account config.

    Mirrors :func:`resolveMarkdownTableMode`
    (``shared/config/markdown-tables.ts`).
    """
    channel_raw = params.get("channel")
    if callable(normalize_channel_id):
        channel = normalize_channel_id(channel_raw)
    else:
        channel = channel_raw.strip().lower() if isinstance(channel_raw, str) else None
    if not channel:
        return "code"
    if callable(get_default_table_modes):
        defaults = get_default_table_modes()
    elif callable(list_channel_plugins):
        # Build a default-mode map from channel plugin metadata.
        defaults = {
            p.id: getattr(p.messaging, "defaultMarkdownTableMode", None)
            for p in (list_channel_plugins() or [])
            if getattr(p.messaging, "defaultMarkdownTableMode", None)
        }
    else:
        defaults = {}
    default_mode = defaults.get(channel) or "code"
    resolved = default_mode
    if params.get("cfg") and channel:
        cfg = params["cfg"]
        channels = cfg.get("channels") if isinstance(cfg, dict) else None
        root = cfg if isinstance(cfg, dict) else {}
        section = (channels or {}).get(channel) if isinstance(channels, dict) else None
        if not isinstance(section, dict):
            section = root.get(channel) if isinstance(root, dict) else None
        if isinstance(section, dict):
            accounts = section.get("accounts")
            if isinstance(accounts, dict):
                account_id = (params.get("accountId") or "").strip().lower() or None
                match = accounts.get(account_id) if account_id else None
                if isinstance(match, dict):
                    mode = (match.get("markdown") or {}).get("tables")
                    if mode in ("off", "bullets", "code", "block"):
                        resolved = mode
            if resolved == default_mode:
                mode = (section.get("markdown") or {}).get("tables")
                if mode in ("off", "bullets", "code", "block"):
                    resolved = mode
    if resolved == "block" and not params.get("supportsBlockTables"):
        return "code"
    return resolved


__all__ = ["MarkdownTableMode", "resolve_markdown_table_mode"]
